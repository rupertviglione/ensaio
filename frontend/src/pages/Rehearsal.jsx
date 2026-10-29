import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Pause, Play, SkipBack, SkipForward, Lightbulb, Flag, Mic, MicOff, Volume2, VolumeX, Check, Pencil, FastForward, Eye, EyeOff, Keyboard } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, errMsg, voiceBody } from "@/lib/api";
import { playClip, loadClip, unlockAudio, outputLatencyMs, stopAudio, audioProgress } from "@/lib/audio";
import { isComplete, localVerdict, normTokens, similar, HELP_RE, NOTE_RE } from "@/lib/match";
import { TranscriptBuffer, alignPos, cleanForTts, splitWords, wordNorm } from "@/lib/transcript";
import { Listener } from "@/lib/listener";
import { ScriptView } from "@/components/script/ScriptView";
import { loadPrefs, savePrefs } from "@/components/script/RehearsalSetup";
import { LineEditor } from "@/components/rehearsal/LineEditor";
import { ShortcutsOverlay, Teleprompter, Kbd } from "@/components/rehearsal/Shortcuts";
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
  const [skipMode, setSkipMode] = useState(false);
  const [editing, setEditing] = useState(null);
  const [showKeys, setShowKeys] = useState(false);
  const [progress, setProgress] = useState(0);
  const [resumeAt, setResumeAt] = useState(null);
  const [micLost, setMicLost] = useState(null);
  const skipRef = useRef(false);
  const keyRef = useRef(() => {});
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
      setSkipMode(!!loadPrefs(sc.id).skipMode);
      skipRef.current = !!loadPrefs(sc.id).skipMode;
      setSession(s);
      setScript(sc);
      const first = s.focus_idxs?.length ? buildPlan(sc.lines, s.focus_idxs, s.character)[0] : s.start_idx;
      const resume = s.turns.length ? Math.max(...s.turns.map((t) => t.line_idx)) : first;
      setIdx(resume);
      idxRef.current = resume;
    }).catch(() => nav("/"));
    api.sttEngines().then((st) => st.messages?.length && setNotice(st.messages.join(" · "))).catch(() => {});
    return () => {
      run.current++;
      stopAudio();
      if (turn.current) clearInterval(turn.current.timer);
      listener.current?.close();
    };
  }, [sessionId, nav]);

  useEffect(() => {
    const f = (e) => keyRef.current(e);
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, []);

  useEffect(() => {
    if (resumeAt == null) return;
    const i = resumeAt;
    setResumeAt(null);
    listener.current?.setActive(true);
    clearFor(i);
    runFrom(i);
  }, [resumeAt]); // eslint-disable-line react-hooks/exhaustive-deps

  const lines = script?.lines || [];
  const mine = session?.character;
  const plan = session?.focus_idxs?.length ? buildPlan(lines, session.focus_idxs, mine) : null;
  const nextOf = (i) => (plan ? plan.find((p) => p > i) ?? lines.length : i + 1);
  const hintMs = (session?.hint_seconds || 5) * 1000;
  const goIdx = (i) => { idxRef.current = i; setIdx(i); setProgress(0); };
  // Modo Saltar: an AI line is played only when it is the cue right before one of the actor's blocks.
  const isCue = (i) => {
    let j = nextOf(i);
    while (j < lines.length && lines[j].kind !== "dialogue") j = nextOf(j);
    return j < lines.length && lines[j].character === mine;
  };
  // Consecutive lines of the actor's character (stage directions in between allowed) form one block.
  const blockOf = (i) => {
    const out = [i];
    for (let j = nextOf(i); j < lines.length; j = nextOf(j)) {
      if (lines[j].kind !== "dialogue") continue;
      if (lines[j].character !== mine) break;
      out.push(j);
    }
    return out;
  };
  const blockText = (b) => b.map((k) => lineText(lines[k])).join(" ");
  const firstMine = (from) => {
    let i = from;
    while (i < lines.length && !(lines[i].kind === "dialogue" && lines[i].character === mine)) i = nextOf(i);
    return i < lines.length ? i : -1;
  };
  // Recogniser vocabulary: rare words, names and foreign words of the current block and the next one (≤100).
  const hintsFrom = (from) => {
    const i = firstMine(from);
    if (i < 0) return [];
    const b = blockOf(i);
    const j = firstMine(nextOf(b[b.length - 1]));
    const ks = [...b, ...(j >= 0 ? blockOf(j) : [])].flatMap((k) => lines[k].keyterms || []);
    return [...new Set(ks)].slice(0, 100);
  };
  const contextFrom = (from) => { const i = firstMine(from); return i < 0 ? [] : blockHints(blockText(blockOf(i))); };
  const clearFor = (from) => { tb.current.clear(); return listener.current?.clear(hintsFrom(from), contextFrom(from)); };

  // Cache holds promises of decoded clips, so a cue never waits on the network or on decoding.
  const getAudio = (l) => {
    const k = `${l.uid}|${l.character}|${lineText(l)}`;
    if (!cache.current.has(k)) {
      const c = script.characters.find((x) => x.name === l.character);
      cache.current.set(k, c ? api.tts({ text: lineText(l), ...voiceBody(c, script.id) }).then(loadClip).catch(() => null) : Promise.resolve(null));
    }
    return cache.current.get(k);
  };
  const getPrompter = (text) => {
    const k = `p:${text}`;
    if (!cache.current.has(k)) cache.current.set(k, api.tts({ text }).then(loadClip).catch(() => null));
    return cache.current.get(k);
  };

  const prefetch = (from) => {
    let n = 0;
    for (let i = from; i < lines.length && n < 10; i = nextOf(i)) {
      const l = lines[i];
      if (l.kind !== "dialogue") continue;
      if (l.character !== mine) { if (!skipRef.current || isCue(i)) getAudio(l); }
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
    const clip = await getPrompter(text);
    if (clip && token === run.current) await playClip(clip);
  };

  const handleResult = async (i, r, token) => {
    if (r.memory_note) toast.success("Guardado na memória do texto", { description: r.memory_note.text });
    if (r.advance) {
      setFeedback(r.turn.severity === "major" ? r.turn : null);
      const b = blockOf(i);
      return runFrom(nextOf(b[b.length - 1]), token);
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
      const r = await api.turn(sessionId, { line_idx: i, line_idxs: blockOf(i), said, mode });
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
    const voiceEndAt = listener.current?.lastVoiceAt || lastWordAt;
    stopTurn();
    setHint(null);
    setLastSaid(said);
    if (!said) { toast("Não ouvi nada. Carrega no microfone para tentares outra vez."); return setPhase("waiting"); }
    const after = nextOf(t.block[t.block.length - 1]);
    const tail = clearFor(after);
    // End detected by content but the very last word not heard yet: give the recogniser ~250 ms to deliver it (judged text only).
    const last = t.words[t.words.length - 1];
    const missing = reason === "match" && tail && last && !said.split(" ").slice(-3).some((w) => similar(wordNorm(w), wordNorm(last)));
    const hasLast = (txt) => txt.split(/\s+/).slice(-3).some((w) => similar(wordNorm(w), wordNorm(last)));
    const judged = missing ? tail(listener.current?.kind === "gemini" ? 1200 : 250, hasLast).then((txt) => extendSaid(said, txt, hasLast)) : Promise.resolve(said);
    const sev = reason === "match" ? localVerdict({ expected: t.expected, said, strictness: session.strictness, memory: script.memory }) : null;
    if (!sev) return judged.then((j) => { if (j !== said) setLastSaid(j); submit(t.i, j, "voz", t.token); });
    setFeedback(null);
    pendingLat.current = { line: t.i, endAt, lastWordAt, voiceEndAt, engine: listener.current?.kind };
    judged.then((j) => {
      if (j !== said) { setLastSaid(j); console.info("[ensaio] última palavra chegou depois do fim:", j.slice(said.length).trim()); }
      return api.turn(sessionId, { line_idx: t.i, line_idxs: t.block, said: j, mode: "voz" });
    }).then((r) => {
      if (r.memory_note) toast.success("Guardado na memória do texto", { description: r.memory_note.text });
      if (t.token !== run.current) return;
      if (r.advance) { if (r.turn.severity === "major") setFeedback(r.turn); return; }
      const token = ++run.current;
      stopAudio();
      stopTurn();
      goIdx(t.i);
      handleResult(t.i, r, token);
    }).catch((e) => console.warn("[ensaio] verificação falhou", errMsg(e)));
    runFrom(after, t.token);
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
      const clip = await getPrompter(h.text);
      if (clip && turn.current === t) {
        tb.current.echoStart(h.text);
        await playClip(clip);
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
    if (t.words.length) setProgress(alignPos(t.words, splitWords(text)) / t.words.length);
    const norm = normTokens(text).join(" ");
    const helps = (norm.match(HELP_RE) || []).length;
    if (helps > t.helps && !(normTokens(t.expected).join(" ").match(HELP_RE) || []).length) { t.helps = helps; giveHint(t); }
    t.note = NOTE_RE.test(norm);
    if (isComplete(t.expected, stripHelp(text, t.expected))) {
      // content says "done" but the actor's voice is still going and the last word hasn't arrived: wait for silence
      const last = t.words[t.words.length - 1];
      const heardLast = last && text.split(/\s+/).slice(-3).some((w) => similar(wordNorm(w), wordNorm(last)));
      if (!heardLast && listener.current?.voiced && performance.now() - (t.awaitAt ??= performance.now()) < 600) { t.awaitSilence = true; return; }
      endTurn("match");
    }
  };

  tickRef.current = () => {
    const t = turn.current;
    if (!t || t.done || t.hinting) return;
    if (t.awaitSilence && (!listener.current?.voiced || performance.now() - t.awaitAt > 600)) return endTurn("match");
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
    if (fresh) clearFor(i);
    const block = blockOf(i);
    const expected = blockText(block);
    stopTurn();
    const t = { i, block, token, expected, words: splitWords(cleanForTts(expected)), hintEnd: 0, helps: 0, since: performance.now(), done: false };
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
      if (l.kind !== "dialogue") { i = nextOf(i); continue; }
      if (l.character !== mine && skipRef.current && !isCue(i)) { i = nextOf(i); continue; }
      goIdx(i);
      if (l.character === mine) return listen(i, token, false);
      setPhase("ai");
      setHint(null);
      prefetch(nextOf(i));
      const clip = await getAudio(l);
      if (token !== run.current) return;
      tb.current.reset();
      tb.current.echoStart(lineText(l), 2500);
      if (clip) {
        const poll = setInterval(() => setProgress(audioProgress()), 200);
        await playClip(clip, () => {
          const p = pendingLat.current;
          if (!p) return;
          pendingLat.current = null;
          const now = performance.now() + outputLatencyMs();
          lat({ type: "actorEnd→aiStart", line: i, engine: p.engine, at: now, ms_voice_to_audio: Math.round(now - p.voiceEndAt),
            ms_voice_to_detect: Math.round(p.endAt - p.voiceEndAt), ms_match_to_audio: Math.round(now - p.endAt), ms_lastword_to_audio: Math.round(now - p.lastWordAt) });
        });
        clearInterval(poll);
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
      onMic: setMicLost,
      onSilence: () => {
        const t = turn.current;
        if (t?.awaitSilence && !t.done) return endTurn("match");
        if (t && !t.done && t.words.length && alignPos(t.words, tb.current.turnWords()) / t.words.length >= 0.5) listener.current?.flush();
      },
    });
    try {
      listener.current = l;
      await l.open(hintsFrom(idxRef.current), contextFrom(idxRef.current));
    } catch {
      l.close();
      listener.current = null;
      toast.error("Sem acesso ao microfone. Podes continuar por escrito.");
      setVoiceOn(false);
    }
  };

  const begin = async () => {
    unlockAudio();
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
    const b = blockOf(idxRef.current);
    clearFor(nextOf(b[b.length - 1]));
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
    clearFor(i);
    if (phase === "ready" || phase === "paused") { run.current++; return; }
    runFrom(i);
  };

  const running = !["ready", "paused", "finishing"].includes(phase);

  const jumpTo = (i) => {
    const t0 = performance.now();
    stopAudio();
    stopTurn();
    setFeedback(null);
    goIdx(i);
    clearFor(i);
    if (running) runFrom(i);
    else begin();
    lat({ type: "jump", line: i, ms: Math.round(performance.now() - t0) });
  };

  const openEdit = (line) => {
    const was = running;
    run.current++;
    stopAudio();
    stopTurn();
    listener.current?.setActive(false);
    if (was) setPhase("paused");
    setEditing({ line, was });
  };

  const saveEdit = async (line, patch) => {
    try {
      const sc = await api.patchLine(script.id, line.uid, patch);
      setScript(sc);
      toast.success(patch.kind === "cut" ? "Fala cortada" : "Alteração guardada no texto");
      return true;
    } catch {
      toast.error("Não foi possível guardar a alteração");
      return false;
    }
  };

  const closeEdit = () => {
    const was = editing?.was;
    setEditing(null);
    if (was) setResumeAt(idxRef.current);
  };

  const toggleSkip = () => setSkipMode((v) => {
    skipRef.current = !v;
    savePrefs(script.id, { skipMode: !v });
    toast(!v ? "Modo Saltar ligado: só a deixa antes de cada fala tua" : "Modo Saltar desligado");
    return !v;
  });
  const toggleText = () => setHideText((v) => { savePrefs(script.id, { hideText: !v }); return !v; });
  const hintNow = () => (phase === "listening" && turn.current ? giveHint(turn.current) : setReveal(true));

  keyRef.current = (e) => {
    const el = e.target;
    if (e.metaKey || e.ctrlKey || e.altKey || editing || showKeys) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(el?.tagName) || el?.isContentEditable || el?.closest?.("[role=dialog]")) return;
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if ((k === " " || k === "Enter") && el?.tagName === "BUTTON") return;
    const act = {
      ArrowRight: () => jump(1), ArrowLeft: () => jump(-1),
      " ": () => (phase === "ready" || phase === "paused" ? begin() : pause()),
      Enter: () => phase === "listening" && endTurn("manual"),
      h: hintNow, e: () => lines[idxRef.current] && openEdit(lines[idxRef.current]), s: toggleSkip, t: toggleText, "?": () => setShowKeys(true),
    }[k];
    if (!act) return;
    e.preventDefault();
    act();
  };

  if (!script) return null;
  const cur = lines[idx];
  const isMine = cur?.character === mine && cur?.kind === "dialogue";
  const curBlock = isMine ? blockOf(idx) : [idx];
  const myIdxs = lines.filter((l) => l.kind === "dialogue" && l.character === mine && (!plan || plan.includes(l.idx))).map((l) => l.idx);
  const doneCount = myIdxs.filter((k) => k < idx || (k === idx && !isMine)).length;
  const names = script.characters.map((c) => c.name);
  const showText = !isMine || !hideText || reveal;
  const myTurn = ["listening", "waiting", "interrupted"].includes(phase) && isMine;

  return (
    <div className="max-w-7xl mx-auto px-6 md:px-10 pt-8 pb-36 grid lg:grid-cols-[1.25fr_1fr] gap-10">
      <section className="flex flex-col items-center gap-4" data-testid="rehearsal-stage">
        <div className="w-full flex items-center justify-between">
          <div>
            <p className="font-mono text-[11px] tracking-[0.3em] text-amber-500">SALA DE ENSAIO</p>
            <h1 className="font-serif text-2xl md:text-3xl font-semibold mt-1">{script.title} <span className="text-stone-500 font-normal">— {mine}</span></h1>
            {plan && <p data-testid="focus-mode-badge" className="mt-1 text-xs font-mono tracking-widest text-rose-300">ZONAS A REVER · {session.focus_idxs.length} FALAS (COM A DEIXA)</p>}
            <EngineBadge engine={engine} hintSeconds={session.hint_seconds || 5} />
            <p data-testid="rehearsal-progress" className="mt-1 text-[10px] font-mono tracking-widest text-stone-500">
              AS TUAS FALAS: {doneCount}/{myIdxs.length}{skipMode && <span data-testid="skip-mode-badge" className="ml-3 text-sky-400">MODO SALTAR</span>}
            </p>
          </div>
          <Button data-testid="finish-rehearsal-btn" onClick={finish} disabled={phase === "finishing"} variant="outline" className="rounded-full border-rose-500/40 text-rose-300 hover:bg-rose-500/10 hover:text-rose-200">
            <Flag className="w-4 h-4 mr-2" /> Terminar
          </Button>
        </div>
        {micLost && (
          <div data-testid="mic-lost-warning" className="w-full flex items-center justify-between gap-3 text-sm text-rose-200 border border-rose-500/40 bg-rose-500/10 rounded-lg px-4 py-2">
            <span>Microfone desligado: {micLost}</span>
            <Button data-testid="mic-reactivate-btn" size="sm" className="rounded-full" onClick={async () => {
              try { await listener.current?.openMic(); toast.success("Microfone reactivado"); } catch { toast.error("Sem acesso ao microfone."); }
            }}>Reactivar microfone</Button>
          </div>
        )}
        {notice && <p data-testid="stt-engine-notice" className="w-full text-xs text-amber-300/90 border border-amber-500/20 rounded-lg px-3 py-2">{notice}</p>}

        <div className="w-full flex-1 flex flex-col items-center justify-center gap-4 py-1">
          {cur && (
            <div className="w-full text-center" data-testid="current-line">
              <div className="flex items-center justify-center gap-3">
                <p className={`font-mono text-sm tracking-[0.3em] uppercase font-bold ${isMine ? "text-amber-400" : "text-sky-400"}`}>
                  {cur.kind !== "dialogue" ? "Rubrica" : isMine ? (curBlock.length > 1 ? `A tua fala · ${curBlock.length} falas seguidas` : "A tua fala") : cur.character}
                </p>
                <button data-testid="current-line-edit-btn" onClick={() => openEdit(cur)} title="Editar esta fala (E)" className="text-stone-500 hover:text-amber-400 transition-colors">
                  <Pencil className="w-4 h-4" />
                </button>
              </div>
              <div data-testid="current-line-text" data-block-size={curBlock.length} data-block-idxs={isMine ? curBlock.join(",") : ""}>
                <Teleprompter testid="current-line-window" texts={curBlock.map((k) => lineText(lines[k]))} progress={progress}
                  className={`font-serif text-2xl md:text-3xl leading-snug mt-3 text-stone-100 ${showText ? "transition-[filter] duration-300" : "blur-md select-none"}`} />
              </div>
              {cur.edited_text && <p className="mt-2 text-[11px] font-mono tracking-widest text-emerald-400" data-testid="current-line-edited">ALTERAÇÃO ACORDADA</p>}
            </div>
          )}
          <MicButton phase={phase} level={level} onClick={onMic} />
          {phase === "listening" && voiceOn && (
            <Button data-testid="done-speaking-btn" onClick={() => endTurn("manual")} variant="outline" className="rounded-full border-amber-500/40 text-amber-300 hover:bg-amber-500/10">
              <Check className="w-4 h-4 mr-2" /> Terminei <Kbd>Enter</Kbd>
            </Button>
          )}
          {hint && phase === "listening" && <HintBox text={hint} />}
          {phase === "listening" && live && (
            <p data-testid="live-transcript" className="text-sm italic text-stone-400 max-w-xl text-center line-clamp-2">
              "{live.split(" ").length > 22 ? `… ${live.split(" ").slice(-22).join(" ")}` : live}"
            </p>
          )}
          {feedback && <FeedbackBox turn={feedback} said={lastSaid} />}
          {(phase === "interrupted" || (phase === "speaking" && feedback?.kind === "line")) && (
            <div className="flex gap-3">
              <Button data-testid="repeat-line-btn" onClick={() => { stopAudio(); setFeedback(null); listen(idxRef.current, ++run.current); }} className="rounded-full">Repetir a fala</Button>
              <Button data-testid="continue-btn" variant="outline" onClick={() => { stopAudio(); setFeedback(null); runFrom(nextOf(idxRef.current)); }} className="rounded-full">Continuar</Button>
            </div>
          )}
        </div>

        <div data-testid="rehearsal-controls" className="fixed bottom-0 inset-x-0 z-30 border-t border-white/[0.07] bg-[#0A0908]/90 backdrop-blur-xl">
          <div className="max-w-7xl mx-auto px-6 md:px-10 py-3">
            <div className="space-y-2.5">
              <div className="max-w-3xl mx-auto"><TextEntry onSubmit={onText} disabled={!myTurn && phase !== "speaking"} /></div>
              <div className="flex flex-wrap items-center justify-center gap-1.5">
                <Ctl testid="prev-line-btn" onClick={() => jump(-1)} icon={SkipBack} label="Anterior" k="←" />
                {phase === "ready" || phase === "paused"
                  ? <Ctl testid="play-btn" onClick={begin} icon={Play} label={phase === "ready" ? "Começar" : "Retomar"} accent k="Espaço" />
                  : <Ctl testid="pause-btn" onClick={pause} icon={Pause} label="Pausa" k="Espaço" />}
                <Ctl testid="next-line-btn" onClick={() => jump(1)} icon={SkipForward} label="Seguinte" k="→" />
                <Ctl testid="hint-btn" onClick={hintNow} icon={Lightbulb} label="Dica" k="H" />
                <Ctl testid="edit-current-btn" onClick={() => cur && openEdit(cur)} icon={Pencil} label="Editar" k="E" />
                <Ctl testid="skip-mode-toggle-btn" onClick={toggleSkip} icon={FastForward} label={skipMode ? "Saltar: ligado" : "Modo Saltar"} k="S" on={skipMode} />
                <Ctl testid="text-toggle-btn" onClick={toggleText} icon={hideText ? EyeOff : Eye} label={hideText ? "Texto escondido" : "Texto visível"} k="T" />
                <Ctl testid="voice-toggle-btn" onClick={() => setVoiceOn((v) => !v)} icon={voiceOn ? Mic : MicOff} label={voiceOn ? "Voz ligada" : "Só escrita"} />
                <Ctl testid="prompter-voice-toggle-btn" onClick={() => setPrompterVoice((v) => { localStorage.setItem("ensaio-prompter-voice", v ? "off" : "on"); return !v; })}
                  icon={prompterVoice ? Volume2 : VolumeX} label={prompterVoice ? "Apontador fala" : "Apontador mudo"} />
                <Ctl testid="shortcuts-btn" onClick={() => setShowKeys(true)} icon={Keyboard} label="Atalhos" k="?" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <aside className="hidden lg:block rounded-2xl border border-white/[0.07] bg-[#141210]/70 backdrop-blur-xl p-4 h-[calc(100vh-20rem)] overflow-y-auto script-scroll sticky top-24" data-testid="rehearsal-script-panel">
        <p className="text-[10px] font-mono tracking-widest text-stone-600 px-2 pb-2">CLICA NUMA FALA PARA SALTAR PARA AQUI OU EDITAR</p>
        <ScriptView lines={plan ? lines.filter((l) => plan.includes(l.idx)) : lines} myCharacter={mine} currentIdx={idx} hideMine={hideText} revealIdx={reveal ? idx : -1}
          hideForeign onJump={jumpTo} onEdit={openEdit} />
      </aside>
      {editing && <LineEditor line={editing.line} names={names} onSave={saveEdit} onClose={closeEdit} />}
      {showKeys && <ShortcutsOverlay onClose={() => setShowKeys(false)} />}
    </div>
  );
}

const lineText = (l) => l.edited_text || l.text;

// said + the words the recogniser delivered after the block closed (found after said's last two words).
const extendSaid = (said, txt, hasLast) => {
  const s = said.split(" ").filter(Boolean);
  const w = (txt || "").split(/\s+/).filter(Boolean);
  if (!hasLast(txt || "")) return said;
  const key = s.slice(-2).map(wordNorm).join(" ");
  for (let k = w.length - 2; k >= 0; k--) {
    if (w.slice(k, k + 2).map(wordNorm).join(" ") === key) {
      const extra = w.slice(k + 2);
      return extra.length && extra.length <= 4 ? `${said} ${extra.join(" ")}` : said;
    }
  }
  // recogniser revised the end ("Dez mil" → "Dez minutos"): take the revised tail for the last words
  const k = Math.max(0, s.length - 3);
  return [...s.slice(0, k), ...w.slice(Math.max(0, w.length - (s.length - k) - 1))].join(" ");
};

const blockHints = (text) => {
  const clean = cleanForTts(text);
  const words = clean.toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, " ").split(/\s+/).filter((w) => w.replace(/-/g, "").length >= 3);
  const phrases = clean.split(/[.!?;]+/).map((p) => p.trim()).filter((p) => p.split(" ").length > 1);
  return [...new Set(words), ...phrases];
};

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

const Ctl = ({ testid, onClick, icon: Icon, label, accent, k, on }) => (
  <button
    data-testid={testid}
    onClick={(e) => { e.currentTarget.blur(); onClick(); }}
    className={`flex items-center gap-1.5 px-3 h-9 rounded-full text-xs border transition-colors ${
      accent ? "bg-amber-500 text-[#0A0908] border-amber-500 hover:bg-amber-400"
        : on ? "border-sky-400/60 text-sky-300 bg-sky-500/10"
        : "border-white/10 text-stone-300 hover:text-amber-400 hover:border-amber-500/40"
    }`}
  >
    <Icon className="w-4 h-4" /> {label}{k && <Kbd>{k}</Kbd>}
  </button>
);
