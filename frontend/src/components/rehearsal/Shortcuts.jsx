import { useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const SHORTCUTS = [
  ["→", "Fala seguinte"], ["←", "Fala anterior"], ["Espaço", "Pausa / retomar"], ["Enter", "Terminei"],
  ["H", "Dica (próximas palavras)"], ["E", "Editar a fala actual"], ["S", "Modo Saltar"], ["T", "Mostrar / esconder o meu texto"], ["?", "Esta lista"],
];

export const Kbd = ({ children }) => (
  <kbd className="ml-1 px-1.5 py-0.5 rounded border border-current/30 font-mono text-[10px] opacity-60 leading-none">{children}</kbd>
);

export const ShortcutsOverlay = ({ onClose }) => (
  <Dialog open onOpenChange={(o) => !o && onClose()}>
    <DialogContent data-testid="shortcuts-overlay" className="bg-[#141210] border-white/10 max-w-md">
      <DialogHeader><DialogTitle className="font-serif text-2xl">Atalhos de teclado</DialogTitle></DialogHeader>
      <ul className="space-y-2">
        {SHORTCUTS.map(([k, label]) => (
          <li key={k} className="flex items-center justify-between text-sm text-stone-300">
            <span>{label}</span><kbd className="px-2 py-1 rounded border border-white/15 bg-white/5 font-mono text-xs">{k}</kbd>
          </li>
        ))}
      </ul>
      <p className="text-xs text-stone-500">Os atalhos ficam desligados enquanto escreves num campo de texto.</p>
    </DialogContent>
  </Dialog>
);

// Fixed-height window: long text scrolls into view progressively (progress 0..1).
const SHORT = 240;
const sentences = (t) => (t.match(/[^.!?…]+[.!?…]+["»”)]*\s*|[^.!?…]+$/g) || [t]).map((x) => x.trim()).filter(Boolean);

// Teleprompter: long lines show only the current sentence with a little context, sliding as the line advances.
export const Teleprompter = ({ texts, progress, className, testid }) => {
  const full = texts.join(" ");
  if (full.length <= SHORT) {
    return (
      <div data-testid={testid} data-mode="full" className={`${className} space-y-3`}>
        {texts.map((t, k) => <p key={k}>{t}</p>)}
      </div>
    );
  }
  const parts = texts.flatMap(sentences);
  const total = parts.reduce((a, p) => a + p.length, 0);
  let acc = 0;
  let cur = parts.length - 1;
  for (let k = 0; k < parts.length; k++) {
    acc += parts[k].length;
    if (acc >= progress * total + 1) { cur = k; break; }
  }
  const win = [cur - 1, cur, cur + 1].filter((k) => k >= 0 && k < parts.length);
  return (
    <div data-testid={testid} data-mode="teleprompter" data-sentence={cur} data-sentences={parts.length}
      className={`${className} h-[168px] overflow-hidden flex flex-col justify-center gap-2 text-xl md:text-2xl`}>
      {win.map((k) => (
        <p key={k} data-testid={k === cur ? "teleprompter-current" : undefined}
          className={`transition-opacity duration-500 animate-in fade-in ${k === cur ? "opacity-100" : "opacity-35 text-lg md:text-xl line-clamp-2"}`}>
          {parts[k]}
        </p>
      ))}
      <p className="text-[10px] font-mono tracking-widest text-stone-600">{cur + 1}/{parts.length}</p>
    </div>
  );
};

export const ClipWindow = ({ progress, children, testid }) => {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const max = el.scrollHeight - el.clientHeight;
    if (max > 0) el.scrollTo({ top: Math.max(0, max * progress - el.clientHeight * 0.15), behavior: "smooth" });
  }, [progress, children]);
  return (
    <div ref={ref} data-testid={testid} className="clip-window h-[170px] overflow-y-auto script-scroll w-full px-2">
      {children}
    </div>
  );
};
