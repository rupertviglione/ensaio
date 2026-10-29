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
