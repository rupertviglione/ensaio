import { useEffect, useRef } from "react";
import { PlayCircle } from "lucide-react";

export const ScriptView = ({ lines, myCharacter, startIdx, onStartHere, currentIdx, hideMine = false, revealIdx }) => {
  const curRef = useRef();
  useEffect(() => {
    curRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [currentIdx]);

  return (
    <div className="space-y-1" data-testid="script-view">
      {lines.map((l) => {
        const mine = l.character === myCharacter;
        const isCur = l.idx === currentIdx;
        if (l.kind === "direction") {
          return (
            <p key={l.idx} ref={isCur ? curRef : null} className="font-serif italic text-stone-500 text-base px-5 py-2">
              {l.text}
            </p>
          );
        }
        const hidden = hideMine && mine && l.idx >= (currentIdx ?? 0) && l.idx !== revealIdx;
        return (
          <div
            key={l.idx}
            ref={isCur ? curRef : null}
            data-testid={`script-line-${l.idx}`}
            className={`group relative rounded-xl px-5 py-3 border-l-2 transition-colors duration-300 ${
              isCur ? "bg-amber-500/[0.14] border-amber-400" :
              mine ? "bg-amber-500/[0.05] border-amber-500/40" : "border-transparent hover:bg-white/[0.03]"
            } ${startIdx === l.idx ? "ring-1 ring-amber-500/50" : ""}`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className={`font-mono text-xs tracking-widest uppercase font-bold ${mine ? "text-amber-400" : "text-sky-400/80"}`}>
                {l.character}
              </span>
              {onStartHere && (
                <button
                  data-testid={`start-here-btn-${l.idx}`}
                  onClick={() => onStartHere(l.idx)}
                  className="opacity-0 group-hover:opacity-100 flex items-center gap-1 text-[11px] font-mono text-stone-400 hover:text-amber-400 transition-opacity"
                >
                  <PlayCircle className="w-3.5 h-3.5" /> COMEÇAR AQUI
                </button>
              )}
            </div>
            <p className={`mt-1 text-base md:text-lg leading-relaxed text-stone-200 transition-[filter] duration-300 ${hidden ? "blur-[6px] select-none" : ""}`}>
              {l.text}
            </p>
          </div>
        );
      })}
    </div>
  );
};
