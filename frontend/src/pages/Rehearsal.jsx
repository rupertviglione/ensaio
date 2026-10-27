import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Pause, Play, SkipBack, SkipForward, Lightbulb, Flag, Mic, MicOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/lib/api";
import { playUrl, stopAudio, Recorder } from "@/lib/audio";
import { ScriptView } from "@/components/script/ScriptView";
import { loadPrefs } from "@/components/script/RehearsalSetup";
import { MicButton } from "@/components/rehearsal/MicButton";
import { TextEntry, FeedbackBox } from "@/components/rehearsal/Parts";

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
  const run = useRef(0);
  const rec = useRef(null);
  const cache = useRef(new Map());
  const idxRef = useRef(0);

  useEffect(() => {
    api.getSession(sessionId).then(async (s) => {
      if (s.status === "finished") return nav(`/resumo/${sessionId}`, { replace: true });
      const sc = await api.getScript(s.script_id);
      setHideText(loadPrefs(sc.id).hideText ?? true);
      setSession(s);
      setScript(sc);
      const resume = s.turns.length ? Math.max(...s.turns.map((t) => t.line_idx)) : s.start_idx;
      setIdx(resume);
      idxRef.current = resume;
    }).catch(() => nav("/"));
    return () => {
      run.current++;
      stopAudio();
      rec.current?.destroy();
    };
  }, [sessionId, nav]);

  const lines = script?.lines || [];
  const mine = session?.character;

  const goIdx = (i) => { idxRef.current = i; setIdx(i); };

  const getAudio = useCallback((l) => {
    if (!cache.current.has(l.idx)) {
      const c = script.characters.find((x) => x.name === l.character);
      cache.current.set(l.idx, api.tts({ text: l.text, voice: c.voice, character: c.name, style: c.style, el_voice_id: c.el_voice_id }).catch(() => null));
    }
    return cache.current.get(l.idx);
  }, [script]);

  const prefetch = (from) => {
    let n = 0;
    for (let i = from; i < lines.length && n < 6; i++) {
      const l = lines[i];
      if (l.kind === "dialogue" && l.character !== mine) { getAudio(l); n++; }
    }
  };

  const finish = async () => {
    run.current++;
    stopAudio();
    rec.current?.cancel();
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
    const url = await api.tts({ text }).catch(() => null);
    if (url && token === run.current) await playUrl(url);
  };

  const submit = async (i, said, mode, token, blob) => {
    setPhase("processing");
    if (said) setLastSaid(said);
    try {
      const r = blob ? await api.voiceTurn(sessionId, i, blob) : await api.turn(sessionId, { line_idx: i, said, mode });
      if (token !== run.current) return;
      if (blob) {
        if (!r.turn) { toast("Não percebi o que disseste. Tenta outra vez."); setPhase("waiting"); return; }
        setLastSaid(r.said);
      }
      if (r.memory_note) toast.success("Guardado na memória do texto", { description: r.memory_note.text });
      if (r.advance) {
        setFeedback(r.turn.severity === "major" ? r.turn : null);
        return runFrom(i + 1, token);
      }
      setFeedback(r.turn);
      if (r.turn.feedback) await speak(r.turn.feedback, token);
      if (token !== run.current) return;
      if (r.turn.kind === "line") setPhase("interrupted");
      else listen(i, token);
    } catch (e) {
      if (token !== run.current) return;
      toast.error(errMsg(e));
      setPhase("waiting");
    }
  };

  const listen = async (i, token) => {
    setPhase("listening");
    setReveal(false);
    prefetch(i + 1);
    if (!voiceOn || !rec.current) return;
    const blob = await rec.current.record({ silenceMs: 900, onLevel: (v) => setLevel((p) => (Math.abs(p - v) > 0.004 ? v : p)) });
    if (token !== run.current) return;
    if (!blob) { setPhase("waiting"); return; }
    submit(i, "", "voz", token, blob);
  };

  const runFrom = async (start, existing) => {
    const token = existing ?? ++run.current;
    let i = start;
    while (i < lines.length) {
      if (token !== run.current) return;
      const l = lines[i];
      goIdx(i);
      if (l.kind !== "dialogue") { i++; continue; }
      if (l.character === mine) return listen(i, token);
      setPhase("ai");
      prefetch(i + 1);
      const url = await getAudio(l);
      if (token !== run.current) return;
      if (url) await playUrl(url);
      i++;
    }
    if (token === run.current) finish();
  };

  const begin = async () => {
    if (voiceOn && !rec.current) {
      try {
        const r = new Recorder();
        await r.init();
        rec.current = r;
      } catch {
        toast.error("Sem acesso ao microfone. Podes continuar por escrito.");
        setVoiceOn(false);
      }
    }
    prefetch(idxRef.current);
    runFrom(idxRef.current);
  };

  const pause = () => { run.current++; stopAudio(); rec.current?.cancel(); setPhase("paused"); };

  const onMic = () => {
    if (phase === "ready" || phase === "paused") return begin();
    if (phase === "listening") return rec.current?.stop();
    if (phase === "waiting" || phase === "interrupted") return listen(idxRef.current, ++run.current);
  };

  const onText = (t) => {
    rec.current?.cancel();
    stopAudio();
    submit(idxRef.current, t, "escrito", ++run.current);
  };

  const jump = (dir) => {
    let i = idxRef.current + dir;
    while (i > 0 && i < lines.length && lines[i].kind !== "dialogue") i += dir;
    i = Math.max(0, Math.min(lines.length - 1, i));
    stopAudio();
    rec.current?.cancel();
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
          </div>
          <Button data-testid="finish-rehearsal-btn" onClick={finish} disabled={phase === "finishing"} variant="outline" className="rounded-full border-rose-500/40 text-rose-300 hover:bg-rose-500/10 hover:text-rose-200">
            <Flag className="w-4 h-4 mr-2" /> Terminar
          </Button>
        </div>

        <div className="w-full flex-1 flex flex-col items-center justify-center gap-8 py-6">
          {cur && (
            <div className="w-full text-center min-h-[140px]" data-testid="current-line">
              <p className={`font-mono text-sm tracking-[0.3em] uppercase font-bold ${isMine ? "text-amber-400" : "text-sky-400"}`}>
                {cur.kind === "direction" ? "Rubrica" : isMine ? "A tua fala" : cur.character}
              </p>
              <p data-testid="current-line-text" className={`font-serif text-2xl md:text-3xl leading-snug mt-4 text-stone-100 transition-[filter] duration-300 ${showText ? "" : "blur-md select-none"}`}>
                {cur.text}
              </p>
            </div>
          )}
          <MicButton phase={phase} level={level} onClick={onMic} />
          {feedback && <FeedbackBox turn={feedback} said={lastSaid} />}
          {(phase === "interrupted" || (phase === "speaking" && feedback?.kind === "line")) && (
            <div className="flex gap-3">
              <Button data-testid="repeat-line-btn" onClick={() => { stopAudio(); setFeedback(null); listen(idxRef.current, ++run.current); }} className="rounded-full">Repetir a fala</Button>
              <Button data-testid="continue-btn" variant="outline" onClick={() => { stopAudio(); setFeedback(null); runFrom(idxRef.current + 1); }} className="rounded-full">Continuar</Button>
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
          </div>
        </div>
      </section>

      <aside className="hidden lg:block rounded-2xl border border-white/[0.07] bg-[#141210]/70 backdrop-blur-xl p-4 h-[calc(100vh-8rem)] overflow-y-auto script-scroll sticky top-24" data-testid="rehearsal-script-panel">
        <ScriptView lines={lines} myCharacter={mine} currentIdx={idx} hideMine={hideText} revealIdx={reveal ? idx : -1} />
      </aside>
    </div>
  );
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
