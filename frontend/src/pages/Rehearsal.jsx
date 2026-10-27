import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Pause, Play, SkipBack, SkipForward, Lightbulb, Flag, Mic, MicOff, Volume2, VolumeX, Check } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/lib/api";
import { playUrl, stopAudio } from "@/lib/audio";
import { isComplete, localVerdict, normTokens, HELP_RE, NOTE_RE } from "@/lib/match";
import { TranscriptBuffer, alignPos, cleanForTts, splitWords } from "@/lib/transcript";
import { Listener } from "@/lib/listener";
import { ScriptView } from "@/components/script/ScriptView";
import { loadPrefs } from "@/components/script/RehearsalSetup";
import { MicButton } from "@/components/rehearsal/MicButton";
import { TextEntry, FeedbackBox, HintBox, EngineBadge } from "@/components/rehearsal/Parts";

const lat = (entry) => {
  window.__ensaioLatency = [...(window.__ensaioLatency || []), entry];
  console.info("[ensaio:latência]", entry);
};

const stripHelp = (text, expected) => {
  if ((normTokens(expected).join(" ").match(HELP_RE) || []).length) return text;
  return text.replace(/\b(texto|linha)\b[!?.,]*/gi, "").replace(/n[aã]o me lembro[!?.,]*/gi, "").replace(/\s+/g, " ").trim();
};

export default function Rehearsal() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [session, setSession] = useState(null);
  const [script, setScript] = useState(null);
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState("ready");
  const [level, setLevel] = useState(0);
  const [feedback, setFeedback] = useState(null);
  const [lastSaid, setLastSaid] = useState("");
  const [reveal, setReveal] = useState(false);
  const [voiceOn, setVoiceOn] = useState(true);
  const [hideText, setHideText] = useState(true);
  const [live, setLive] = useState("");
  const [hint, setHint] = useState(null);
  const [engine, setEngine] = useState(null);
  const [notice, setNotice] = useState("");
  const [prompterVoice, setPrompterVoice] = useState(() => localStorage.getItem("ensaio-prompter-voice") !== "off");
  const run = useRef(0);
  const listener = useRef(null);
  const tb = useRef(new TranscriptBuffer());
  const turn = useRef(null);
  const cache = useRef(new Map());
  const idxRef = useRef(0);
  const pendingLat = useRef(null);
  const checkRef = useRef(() => {});
  const tickRef = useRef(() => {});

  useEffect(() => {
    api.getSession(sessionId).then(async (s) => {
      if (s.status === "finished") return nav(`/resumo/${sessionId}`, { replace: true });
      const sc = await api.getScript(s.script_id);
      setHideText(loadPrefs(sc.id).hideText ?? true);
      setSession(s);
      setScript(sc);
      const first = s.focus_idxs?.length ? buildPlan(sc.lines, s.focus_idxs, s.character)[0] : s.start_idx;
      const resume = s.turns.length ? Math.max(...s.turns.map((t) => t.line_idx)) : first;
      setIdx(resume);
      idxRef.current = resume;
    }).catch(() => nav("/"));
    api.elevenStatus().then((st) => st.messages?.length && setNotice(st.messages.join(" · "))).catch(() => {});
    return () => {
      run.current++;
      stopAudio();
      if (turn.current) clearInterval(turn.current.timer);
      listener.current?.close();
    };
  }, [sessionId, nav]);

  const lines = script?.lines || [];
  const mine = session?.character;
  const plan = session?.focus_idxs?.length ? buildPlan(lines, session.focus_idxs, mine) : null;
  const nextOf = (i) => (plan ? plan.find((p) => p > i) ?? lines.length : i + 1);
  const hintMs = (session?.hint_seconds || 5) * 1000;
  const goIdx = (i) => { idxRef.current = i; setIdx(i); };

  const getAudio = (l) => {
    if (!cache.current.has(l.idx)) {
      const c = script.characters.find((x) => x.name === l.character);
      cache.current.set(l.idx, api.tts({ text: lineText(l), voice: c.voice, character: c.name, style: c.style, el_voice_id: c.el_voice_id }).catch(() => null));
    }
    return cache.current.get(l.idx);
  };
  const getPrompter = (text) => {
    const k = `p:${text}`;
    if (!cache.current.has(k)) cache.current.set(k, api.tts({ text }).catch(() => null));
    return cache.current.get(k);
  };

  const prefetch = (from) => {
    let n = 0;
    for (let i = from; i < lines.length && n < 6; i = nextOf(i)) {
      const l = lines[i];
      if (l.kind !== "dialogue") continue;
      if (l.character !== mine) getAudio(l);
      else if (prompterVoice) getPrompter(splitWords(cleanForTts(lineText(l))).slice(0, 3).join(" "));
      n++;
    }
  };

  const stopTurn = () => {
    if (turn.current) { clearInterval(turn.current.timer); turn.current.done = true; }
    turn.current = null;
  };

  const finish = async () => {
    run.current++;
    stopAudio();
    stopTurn();
    setPhase("finishing");
    try {
      await api.finish(sessionId);
      nav(`/resumo/${sessionId}`);
    } catch (e) {
      toast.error(errMsg(e));
      setPhase("paused");
    }
  };

  const speak = async (text, token) => {
    setPhase("speaking");
    const url = await getPrompter(text);
    if (url && token === run.current) await playUrl(url);
  };

  const handleResult = async (i, r, token) => {
    if (r.memory_note) toast.success("Guardado na memória do texto", { description: r.memory_note.text });
    if (r.advance) {
      setFeedback(r.turn.severity === "major" ? r.turn : null);
      return runFrom(nextOf(i), token);
    }
    setFeedback(r.turn);
    if (r.turn.feedback && prompterVoice) await speak(r.turn.feedback, token);
    if (token !== run.current) return;
    if (r.turn.kind === "line") setPhase("interrupted");
    else listen(i, token);
  };

  const submit = async (i, said, mode, token) => {
    setPhase("processing");
    setLastSaid(said);
    try {
      const r = await api.turn(sessionId, { line_idx: i, said, mode });
      if (token !== run.current) return;
      await handleResult(i, r, token);
    } catch (e) {
      if (token !== run.current) return;
      toast.error(errMsg(e));
      setPhase("waiting");
    }
  };

  // Single completion path: content match (instant, local) or "Terminei" / note → server.
  const endTurn = (reason) => {
    const t = turn.current;
    if (!t || t.done) return;
    const said = stripHelp(tb.current.turnWords().join(" "), t.expected);
    const endAt = performance.now();
    const lastWordAt = tb.current.lastWordAt();
    stopTurn();
    listener.current?.commit();
    setHint(null);
    setLastSaid(said);
    if (!said) { toast("Não ouvi nada. Carrega no microfone para tentares outra vez."); return setPhase("waiting"); }
    const sev = reason === "match" ? localVerdict({ expected: t.expected, said, strictness: session.strictness, memory: script.memory }) : null;
    if (!sev) return submit(t.i, said, "voz", t.token);
    setFeedback(null);
    pendingLat.current = { line: t.i, endAt, lastWordAt };
    api.turn(sessionId, { line_idx: t.i, said, mode: "voz" }).then((r) => {
      if (r.memory_note) toast.success("Guardado na memória do texto", { description: r.memory_note.text });
      if (t.token !== run.current) return;
      if (r.advance) { if (r.turn.severity === "major") setFeedback(r.turn); return; }
      const token = ++run.current;
      stopAudio();
      stopTurn();
      goIdx(t.i);
      handleResult(t.i, r, token);
    }).catch((e) => console.warn("[ensaio] verificação falhou", errMsg(e)));
    runFrom(nextOf(t.i), t.token);
  };

  const nextHint = (t) => {
    const pos = alignPos(t.words, tb.current.turnWords());
    const start = Math.max(pos, t.hintEnd);
    return { start, text: t.words.slice(start, start + 3).join(" ") };
  };

  const giveHint = async (t) => {
    const h = nextHint(t);
    t.since = performance.now();
    if (!h.text) return;
    t.hintEnd = h.start + 3;
    t.hinting = true;
    t.prefetched = false;
    setHint(h.text);
    if (prompterVoice) {
      const url = await getPrompter(h.text);
      if (url && turn.current === t) {
        tb.current.echoStart(h.text);
        await playUrl(url);
        tb.current.echoEnd(400);
      }
    }
    t.hinting = false;
    t.since = performance.now();
  };

  checkRef.current = () => {
    const t = turn.current;
    if (!t || t.done) return;
    const text = tb.current.turnWords().join(" ");
    setLive(text);
    const norm = normTokens(text).join(" ");
    const helps = (norm.match(HELP_RE) || []).length;
    if (helps > t.helps && !(normTokens(t.expected).join(" ").match(HELP_RE) || []).length) { t.helps = helps; giveHint(t); }
    t.note = NOTE_RE.test(norm);
    if (isComplete(t.expected, stripHelp(text, t.expected))) endTurn("match");
  };

  tickRef.current = () => {
    const t = turn.current;
    if (!t || t.done || t.hinting) return;
    const silent = performance.now() - Math.max(tb.current.lastChange, t.since);
    if (t.note && silent > 2500) return endTurn("note");
    if (prompterVoice && !t.prefetched && silent > hintMs - 1500) { t.prefetched = true; getPrompter(nextHint(t).text); }
    if (silent >= hintMs) giveHint(t);
  };

  const listen = (i, token, fresh = true) => {
    setPhase("listening");
    setReveal(false);
    setHint(null);
    prefetch(nextOf(i));
    if (!voiceOn || !listener.current) { setLive(""); return; }
    if (fresh) tb.current.reset();
    const expected = lineText(lines[i]);
    stopTurn();
    const t = { i, token, expected, words: splitWords(cleanForTts(expected)), hintEnd: 0, helps: 0, since: performance.now(), done: false };
    t.timer = setInterval(() => tickRef.current(), 200);
    turn.current = t;
    setLive("");
    checkRef.current();
  };

  const runFrom = async (start, existing) => {
    const token = existing ?? ++run.current;
    stopTurn();
    let i = start;
    while (i < lines.length) {
      if (token !== run.current) return;
      const l = lines[i];
      goIdx(i);
      if (l.kind !== "dialogue") { i = nextOf(i); continue; }
      if (l.character === mine) return listen(i, token, false);
      setPhase("ai");
      setHint(null);
      prefetch(nextOf(i));
      const url = await getAudio(l);
      if (token !== run.current) return;
      tb.current.reset();
      tb.current.echoStart(lineText(l), 2500);
      if (url) {
        await playUrl(url, () => {
          const p = pendingLat.current;
          if (!p) return;
          pendingLat.current = null;
          const now = performance.now();
          lat({ type: "actorEnd→aiStart", line: i, ms_match_to_audio: Math.round(now - p.endAt), ms_lastword_to_audio: Math.round(now - p.lastWordAt) });
        });
      }
      tb.current.echoEnd(500);
      const lc = listener.current;
      if (lc) lat({ type: "aiEnd→micReady", line: i, engine: lc.kind, ms_since_last_chunk: Math.round(performance.now() - lc.lastChunkAt), capturing: performance.now() - lc.lastChunkAt < 250 });
      i = nextOf(i);
    }
    if (token === run.current) finish();
  };

  const openMic = async () => {
    if (!voiceOn || listener.current) return listener.current?.setActive(true);
    setPhase("opening");
    const l = new Listener({
      onText: (text) => { if (tb.current.update(text)) checkRef.current(); },
      onLevel: (v) => setLevel((p) => (Math.abs(p - v) > 0.004 ? v : p)),
      onNotice: (msg) => { setNotice(msg); toast.warning(msg); },
      onEngine: setEngine,
    });
    try {
      await l.open();
      listener.current = l;
    } catch {
      l.close();
      toast.error("Sem acesso ao microfone. Podes continuar por escrito.");
      setVoiceOn(false);
    }
  };

  const begin = async () => {
    await openMic();
    prefetch(idxRef.current);
    runFrom(idxRef.current);
  };

  const pause = () => { run.current++; stopAudio(); stopTurn(); listener.current?.setActive(false); setPhase("paused"); };

  const onMic = () => {
    if (phase === "ready" || phase === "paused") return begin();
    if (phase === "listening") return endTurn("manual");
    if (phase === "waiting" || phase === "interrupted") return listen(idxRef.current, ++run.current);
  };

  const onText = (t) => {
    stopTurn();
    stopAudio();
    submit(idxRef.current, t, "escrito", ++run.current);
  };

  const jump = (dir) => {
    let i;
    if (plan) {
      const pos = plan.indexOf(idxRef.current);
      i = plan[Math.max(0, Math.min(plan.length - 1, (pos < 0 ? 0 : pos) + dir))];
    } else {
      i = idxRef.current + dir;
      while (i > 0 && i < lines.length && lines[i].kind !== "dialogue") i += dir;
      i = Math.max(0, Math.min(lines.length - 1, i));
    }
    stopAudio();
    stopTurn();
    setFeedback(null);
    goIdx(i);
    if (phase === "ready" || phase === "paused") { run.current++; return; }
    runFrom(i);
  };

  if (!script) return null;
  const cur = lines[idx];
  const isMine = cur?.character === mine;
  const showText = !isMine || !hideText || reveal;
  const myTurn = ["listening", "waiting", "interrupted"].includes(phase) && isMine;

  return (
    <div className="max-w-7xl mx-auto px-6 md:px-10 py-8 grid lg:grid-cols-[1.25fr_1fr] gap-10">
      <section className="flex flex-col items-center gap-8 lg:min-h-[calc(100vh-8rem)]" data-testid="rehearsal-stage">
        <div className="w-full flex items-center justify-between">
          <div>
            <p className="font-mono text-[11px] tracking-[0.3em] text-amber-500">SALA DE ENSAIO</p>
            <h1 className="font-serif text-2xl md:text-3xl font-semibold mt-1">{script.title} <span className="text-stone-500 font-normal">— {mine}</span></h1>
            {plan && <p data-testid="focus-mode-badge" className="mt-1 text-xs font-mono tracking-widest text-rose-300">ZONAS A REVER · {session.focus_idxs.length} FALAS (COM A DEIXA)</p>}
            <EngineBadge engine={engine} hintSeconds={session.hint_seconds || 5} />
          </div>
          <Button data-testid="finish-rehearsal-btn" onClick={finish} disabled={phase === "finishing"} variant="outline" className="rounded-full border-rose-500/40 text-rose-300 hover:bg-rose-500/10 hover:text-rose-200">
            <Flag className="w-4 h-4 mr-2" /> Terminar
          </Button>
        </div>
        {notice && <p data-testid="eleven-permission-warning" className="w-full text-xs text-amber-300/90 border border-amber-500/20 rounded-lg px-3 py-2">{notice}</p>}

        <div className="w-full flex-1 flex flex-col items-center justify-center gap-8 py-6">
          {cur && (
            <div className="w-full text-center min-h-[140px]" data-testid="current-line">
              <p className={`font-mono text-sm tracking-[0.3em] uppercase font-bold ${isMine ? "text-amber-400" : "text-sky-400"}`}>
                {cur.kind === "direction" ? "Rubrica" : isMine ? "A tua fala" : cur.character}
              </p>
              <p data-testid="current-line-text" className={`font-serif text-2xl md:text-3xl leading-snug mt-4 text-stone-100 ${showText ? "transition-[filter] duration-300" : "blur-md select-none"}`}>
                {lineText(cur)}
              </p>
              {cur.edited_text && <p className="mt-2 text-[11px] font-mono tracking-widest text-emerald-400" data-testid="current-line-edited">ALTERAÇÃO ACORDADA</p>}
            </div>
          )}
          <MicButton phase={phase} level={level} onClick={onMic} />
          {phase === "listening" && voiceOn && (
            <Button data-testid="done-speaking-btn" onClick={() => endTurn("manual")} variant="outline" className="rounded-full border-amber-500/40 text-amber-300 hover:bg-amber-500/10">
              <Check className="w-4 h-4 mr-2" /> Terminei
            </Button>
          )}
          {hint && phase === "listening" && <HintBox text={hint} />}
          {phase === "listening" && live && (
            <p data-testid="live-transcript" className="text-sm italic text-stone-400 max-w-xl text-center">"{live}"</p>
          )}
          {feedback && <FeedbackBox turn={feedback} said={lastSaid} />}
          {(phase === "interrupted" || (phase === "speaking" && feedback?.kind === "line")) && (
            <div className="flex gap-3">
              <Button data-testid="repeat-line-btn" onClick={() => { stopAudio(); setFeedback(null); listen(idxRef.current, ++run.current); }} className="rounded-full">Repetir a fala</Button>
              <Button data-testid="continue-btn" variant="outline" onClick={() => { stopAudio(); setFeedback(null); runFrom(nextOf(idxRef.current)); }} className="rounded-full">Continuar</Button>
            </div>
          )}
        </div>

        <div className="w-full space-y-4">
          <TextEntry onSubmit={onText} disabled={!myTurn && phase !== "speaking"} />
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Ctl testid="prev-line-btn" onClick={() => jump(-1)} icon={SkipBack} label="Anterior" />
            {phase === "ready" || phase === "paused"
              ? <Ctl testid="play-btn" onClick={begin} icon={Play} label={phase === "ready" ? "Começar" : "Retomar"} accent />
              : <Ctl testid="pause-btn" onClick={pause} icon={Pause} label="Pausa" />}
            <Ctl testid="next-line-btn" onClick={() => jump(1)} icon={SkipForward} label="Seguinte" />
            <Ctl testid="hint-btn" onClick={() => setReveal(true)} icon={Lightbulb} label="Dica" />
            <Ctl testid="voice-toggle-btn" onClick={() => setVoiceOn((v) => !v)} icon={voiceOn ? Mic : MicOff} label={voiceOn ? "Voz ligada" : "Só escrita"} />
            <Ctl testid="prompter-voice-toggle-btn" onClick={() => setPrompterVoice((v) => { localStorage.setItem("ensaio-prompter-voice", v ? "off" : "on"); return !v; })}
              icon={prompterVoice ? Volume2 : VolumeX} label={prompterVoice ? "Apontador fala" : "Apontador mudo"} />
          </div>
        </div>
      </section>

      <aside className="hidden lg:block rounded-2xl border border-white/[0.07] bg-[#141210]/70 backdrop-blur-xl p-4 h-[calc(100vh-8rem)] overflow-y-auto script-scroll sticky top-24" data-testid="rehearsal-script-panel">
        <ScriptView lines={plan ? lines.filter((l) => plan.includes(l.idx)) : lines} myCharacter={mine} currentIdx={idx} hideMine={hideText} revealIdx={reveal ? idx : -1} />
      </aside>
    </div>
  );
}

const lineText = (l) => l.edited_text || l.text;

function buildPlan(lines, focus, mine) {
  const steps = new Set();
  focus.forEach((f) => {
    if (!lines[f]) return;
    let c = f - 1;
    while (c >= 0 && lines[c].kind !== "dialogue") c--;
    if (c >= 0 && lines[c].character !== mine) steps.add(c);
    steps.add(f);
  });
  return [...steps].sort((a, b) => a - b);
}

const Ctl = ({ testid, onClick, icon: Icon, label, accent }) => (
  <button
    data-testid={testid}
    onClick={onClick}
    className={`flex items-center gap-2 px-4 h-10 rounded-full text-sm border transition-colors ${
      accent ? "bg-amber-500 text-[#0A0908] border-amber-500 hover:bg-amber-400" : "border-white/10 text-stone-300 hover:text-amber-400 hover:border-amber-500/40"
    }`}
  >
    <Icon className="w-4 h-4" /> {label}
  </button>
);
