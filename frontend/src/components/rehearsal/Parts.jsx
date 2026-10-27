import { useState } from "react";
import { SendHorizontal } from "lucide-react";
import { Input } from "@/components/ui/input";

export const TextEntry = ({ onSubmit, disabled }) => {
  const [v, setV] = useState("");
  const send = (e) => {
    e.preventDefault();
    if (!v.trim()) return;
    onSubmit(v.trim());
    setV("");
  };
  return (
    <form onSubmit={send} className="flex gap-2 w-full" data-testid="text-entry-form">
      <Input
        data-testid="text-entry-input"
        value={v}
        onChange={(e) => setV(e.target.value)}
        disabled={disabled}
        placeholder="Escreve a tua fala ou uma nota…"
        className="h-12 bg-[#141210] rounded-full px-5"
      />
      <button
        type="submit"
        data-testid="text-entry-submit"
        disabled={disabled}
        className="h-12 w-12 shrink-0 rounded-full bg-amber-500 text-[#0A0908] flex items-center justify-center hover:bg-amber-400 transition-colors disabled:opacity-40"
      >
        <SendHorizontal className="w-5 h-5" />
      </button>
    </form>
  );
};

const SEV = {
  major: "border-rose-500/60 bg-rose-500/[0.07]",
  minor: "border-amber-500/50 bg-amber-500/[0.06]",
  none: "border-emerald-500/50 bg-emerald-500/[0.05]",
};

export const HintBox = ({ text }) => (
  <div data-testid="hint-display" className="rise rounded-full border border-sky-400/40 bg-sky-500/[0.07] px-5 py-2 text-sky-200 font-serif text-lg">
    <span className="font-mono text-[10px] tracking-[0.3em] text-sky-400 mr-3">DICA</span>{text}…
  </div>
);

const ENGINE = { scribe: "Escuta em tempo real · ElevenLabs Scribe", webspeech: "Escuta do browser (motor anterior)", none: "Sem reconhecimento de voz" };

export const EngineBadge = ({ engine, hintSeconds }) => (
  <p data-testid="stt-engine-badge" className="mt-1 text-[10px] font-mono tracking-widest text-stone-500 uppercase">
    {engine ? ENGINE[engine] : "Microfone fechado"} · dica após {hintSeconds}s de silêncio
  </p>
);

export const FeedbackBox = ({ turn, said }) => (
  <div data-testid="feedback-box" className={`rise w-full rounded-2xl border-l-2 px-6 py-5 ${SEV[turn.severity] || SEV.none}`}>
    {said && (
      <p className="text-xs text-stone-500 mb-2">
        <span className="font-mono tracking-widest">OUVI:</span> <span className="italic text-stone-400">"{said}"</span>
      </p>
    )}
    {turn.feedback && <p data-testid="feedback-text" className="text-stone-100 text-base">{turn.feedback}</p>}
    {turn.differences?.length > 0 && (
      <ul className="mt-3 space-y-1 text-sm">
        {turn.differences.map((d, i) => (
          <li key={i} className="text-stone-400">
            <span className="font-mono text-[10px] uppercase text-amber-400 mr-2">{d.type}</span>
            <span className="text-emerald-300">"{d.expected}"</span> → <span className="text-rose-300">"{d.said || "—"}"</span>
          </li>
        ))}
      </ul>
    )}
  </div>
);
