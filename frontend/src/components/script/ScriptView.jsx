import { useEffect, useRef, useState } from "react";
import { PlayCircle, CornerDownRight, Pencil } from "lucide-react";

const LineActions = ({ l, onJump, onEdit }) => (
  <div className="flex gap-2 mt-2" data-testid={`line-actions-${l.idx}`}>
    {l.kind === "dialogue" && (
      <button data-testid={`jump-here-btn-${l.idx}`} onClick={(e) => { e.stopPropagation(); onJump(l.idx); }}
        className="flex items-center gap-1 text-[11px] font-mono tracking-widest px-3 py-1 rounded-full bg-amber-500 text-[#0A0908] hover:bg-amber-400">
        <CornerDownRight className="w-3.5 h-3.5" /> SALTAR PARA AQUI
      </button>
    )}
    <button data-testid={`line-edit-btn-${l.idx}`} onClick={(e) => { e.stopPropagation(); onEdit(l); }}
      className="flex items-center gap-1 text-[11px] font-mono tracking-widest px-3 py-1 rounded-full border border-white/15 text-stone-300 hover:text-amber-400">
      <Pencil className="w-3.5 h-3.5" /> EDITAR
    </button>
  </div>
);

const spoken = (l) => l && (l.kind === "dialogue" || l.kind === "cut");

export const ScriptView = ({ lines, myCharacter, startIdx, onStartHere, currentIdx, hideMine = false, revealIdx, hideForeign = false, onJump, onEdit }) => {
  const curRef = useRef();
  const [sel, setSel] = useState(null);
  useEffect(() => {
    const el = curRef.current;
    const box = el?.closest(".script-scroll");
    if (box) {
      const top = box.scrollTop + el.getBoundingClientRect().top - box.getBoundingClientRect().top;
      box.scrollTo({ top: top - box.clientHeight / 2 + el.clientHeight / 2, behavior: "smooth" });
    } else el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [currentIdx]);
  const shown = hideForeign ? lines.filter((l) => l.kind !== "foreign") : lines;
  const pick = onJump ? (l) => setSel((s) => (s === l.idx ? null : l.idx)) : null;

  return (
    <div className="space-y-1" data-testid="script-view">
      {shown.map((l, k) => {
        const mine = l.character === myCharacter;
        const isCur = l.idx === currentIdx;
        const actions = pick && sel === l.idx && <LineActions l={l} onJump={(i) => { setSel(null); onJump(i); }} onEdit={(x) => { setSel(null); onEdit(x); }} />;
        if (l.kind === "direction" || l.kind === "foreign") {
          return (
            <div key={l.idx} ref={isCur ? curRef : null} data-testid={`script-line-${l.idx}`} data-kind={l.kind} onClick={() => pick?.(l)}
              className={`px-5 py-2 ${pick ? "cursor-pointer hover:bg-white/[0.03] rounded-xl" : ""}`}>
              <p className={`font-serif italic text-base ${l.kind === "foreign" ? "text-stone-500 text-sm" : "text-stone-500"}`}>
                {l.kind === "foreign" && <span className="not-italic font-mono text-[10px] tracking-widest text-stone-400 mr-2">NÃO PERTENCE</span>}
                {l.text}
              </p>
              {actions}
            </div>
          );
        }
        const prev = shown[k - 1];
        const grouped = spoken(prev) && prev.character === l.character;
        const cut = l.kind === "cut";
        const hidden = !cut && hideMine && mine && l.idx >= (currentIdx ?? 0) && l.idx !== revealIdx;
        return (
          <div
            key={l.idx}
            ref={isCur ? curRef : null}
            data-testid={`script-line-${l.idx}`}
            data-kind={l.kind}
            data-grouped={grouped ? "true" : "false"}
            onClick={() => pick?.(l)}
            className={`group relative rounded-xl px-5 border-l-2 transition-colors duration-300 ${grouped ? "pt-1 pb-3 -mt-1" : "py-3"} ${pick ? "cursor-pointer" : ""} ${
              isCur ? "bg-amber-500/[0.14] border-amber-400" : cut ? "border-rose-500/30 opacity-60" : l.edited_text ? "bg-emerald-500/[0.05] border-emerald-500/50" :
              mine ? "bg-amber-500/[0.05] border-amber-500/40" : "border-transparent hover:bg-white/[0.03]"
            } ${startIdx === l.idx ? "ring-1 ring-amber-500/50" : ""}`}
          >
            <div className={`flex items-center justify-between gap-3 ${grouped ? "h-0 overflow-visible" : ""}`}>
              {!grouped && (
                <span data-testid={`script-line-name-${l.idx}`} className={`font-mono text-xs tracking-widest uppercase font-bold ${mine ? "text-amber-400" : "text-sky-400/80"}`}>
                  {l.character}{cut && <span className="ml-2 text-rose-400/80 font-normal">· CORTADA</span>}
                </span>
              )}
              {onStartHere && !cut && (
                <button
                  data-testid={`start-here-btn-${l.idx}`}
                  onClick={() => onStartHere(l.idx)}
                  className="opacity-0 group-hover:opacity-100 flex items-center gap-1 text-[11px] font-mono text-stone-400 hover:text-amber-400 transition-opacity"
                >
                  <PlayCircle className="w-3.5 h-3.5" /> COMEÇAR AQUI
                </button>
              )}
            </div>
            <p data-testid={`script-line-text-${l.idx}`} className={`mt-1 text-base md:text-lg leading-relaxed ${cut ? "line-through text-stone-500" : "text-stone-200"} ${hidden ? "blur-[6px] select-none" : "transition-[filter] duration-300"}`}>
              {l.edited_text || l.text}
            </p>
            {l.edited_text && (
              <p data-testid={`script-line-original-${l.idx}`} className={`mt-1 text-xs text-stone-500 ${hidden ? "blur-[6px] select-none" : ""}`}>
                <span className="font-mono tracking-widest text-emerald-400 mr-2">ALTERADO</span>
                <span className="line-through">{l.text}</span>
              </p>
            )}
            {actions}
          </div>
        );
      })}
    </div>
  );
};
