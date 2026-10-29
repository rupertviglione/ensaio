import { useState } from "react";
import { Scissors, Save, Loader2, Undo2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

// In-rehearsal editor: one click on a character chip reassigns and saves; "Cortada" saves at once.
export const LineEditor = ({ line, names, onSave, onClose }) => {
  const [text, setText] = useState(line.edited_text || line.text);
  const [busy, setBusy] = useState(false);
  const save = async (patch) => {
    setBusy(true);
    const ok = await onSave(line, patch);
    setBusy(false);
    if (ok) onClose();
  };
  const cut = line.kind === "cut";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="line-editor" className="bg-[#141210] border-white/10 max-w-xl">
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl">Editar fala</DialogTitle>
          <DialogDescription className="text-stone-500 text-xs">Fica guardado no texto. A escuta está em pausa enquanto editas.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <p className="font-mono text-[10px] tracking-[0.3em] text-stone-500">QUEM DIZ (UM CLIQUE GUARDA)</p>
          <div className="flex flex-wrap gap-2">
            {names.map((n) => (
              <button key={n} data-testid={`line-editor-character-${n}`} disabled={busy} onClick={() => n !== line.character && save({ character: n })}
                className={`text-xs font-mono tracking-widest px-3 py-1.5 rounded-full border transition-colors ${n === line.character ? "border-amber-500 text-amber-400 bg-amber-500/10" : "border-white/10 text-stone-300 hover:border-sky-400/50 hover:text-sky-300"}`}>
                {n}
              </button>
            ))}
            <button data-testid="line-editor-direction" disabled={busy} onClick={() => save({ kind: "direction" })}
              className="text-xs px-3 py-1.5 rounded-full border border-white/10 text-stone-400 hover:text-stone-100 italic">rubrica</button>
          </div>
        </div>
        <Textarea data-testid="line-editor-text" value={text} onChange={(e) => setText(e.target.value)} className="bg-[#0A0908] min-h-[120px] font-serif text-lg" autoFocus />
        <div className="flex flex-wrap justify-between gap-2">
          <Button data-testid="line-editor-cut" variant="outline" disabled={busy} onClick={() => save({ kind: cut ? "dialogue" : "cut" })}
            className="rounded-full border-rose-500/40 text-rose-300 hover:bg-rose-500/10">
            {cut ? <><Undo2 className="w-4 h-4 mr-2" />Repor fala</> : <><Scissors className="w-4 h-4 mr-2" />Cortada</>}
          </Button>
          <div className="flex gap-2">
            <Button data-testid="line-editor-cancel" variant="outline" onClick={onClose} className="rounded-full">Cancelar</Button>
            <Button data-testid="line-editor-save" disabled={busy || !text.trim() || text.trim() === (line.edited_text || line.text)} onClick={() => save({ text })} className="rounded-full">
              {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}Guardar texto
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
