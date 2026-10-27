import { Mic, Square, Loader2, RotateCcw } from "lucide-react";

const STATUS = {
  ready: "Pronto para começar",
  ai: "A contracena…",
  listening: "A ouvir-te…",
  processing: "A verificar…",
  speaking: "O apontador está a falar",
  waiting: "Carrega para dizeres a fala",
  interrupted: "Repete ou continua",
  paused: "Em pausa",
  finishing: "A preparar o resumo…",
};

const Wave = () => (
  <div className="flex items-center gap-1 h-10">
    {[0, 1, 2, 3, 4, 5, 6].map((i) => (
      <span key={i} className="wave-bar w-1.5 h-full rounded-full bg-sky-400" style={{ animationDelay: `${i * 0.11}s` }} />
    ))}
  </div>
);

export const MicButton = ({ phase, level, onClick }) => {
  const listening = phase === "listening";
  const busy = phase === "processing" || phase === "finishing";
  const scale = listening ? 1 + Math.min(level * 8, 0.35) : 1;
  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative w-36 h-36 flex items-center justify-center">
        {listening && <span className="mic-ring absolute inset-0 rounded-full border-2 border-amber-400" />}
        {listening && <span className="mic-ring absolute inset-0 rounded-full border-2 border-amber-400" style={{ animationDelay: "0.8s" }} />}
        <button
          data-testid="mic-toggle-button"
          onClick={onClick}
          disabled={busy || phase === "ai" || phase === "speaking"}
          style={{ transform: `scale(${scale})` }}
          className={`relative w-32 h-32 rounded-full flex items-center justify-center transition-[transform,background-color,box-shadow] duration-150 disabled:cursor-default ${
            listening ? "bg-amber-500 text-[#0A0908] shadow-[0_0_60px_rgba(245,158,11,0.45)]"
              : phase === "ai" || phase === "speaking" ? "bg-sky-500/10 border border-sky-400/40"
              : "bg-[#1C1917] border border-amber-500/40 text-amber-400 hover:bg-amber-500/10"
          }`}
        >
          {busy ? <Loader2 className="w-10 h-10 animate-spin text-amber-400" />
            : phase === "ai" || phase === "speaking" ? <Wave />
            : listening ? <Square className="w-9 h-9" fill="currentColor" />
            : phase === "interrupted" ? <RotateCcw className="w-10 h-10" />
            : <Mic className="w-11 h-11" />}
        </button>
      </div>
      <p data-testid="rehearsal-status" className="font-mono text-xs tracking-[0.25em] uppercase text-stone-400">{STATUS[phase]}</p>
    </div>
  );
};
