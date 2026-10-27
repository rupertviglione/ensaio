import { useState } from "react";
import { Plus, Trash2, Save, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, errMsg } from "@/lib/api";

const NEW = "__nova__";

const LineRow = ({ l, i, names, onChange, onRemove, onInsert }) => (
  <div data-testid={`edit-line-${i}`} className="group rounded-xl border border-white/[0.07] bg-[#141210] p-3 space-y-2">
    <div className="flex flex-wrap items-center gap-2">
      <select
        data-testid={`edit-line-character-${i}`}
        value={l.kind === "direction" ? "" : l.character || ""}
        onChange={(e) => {
          const v = e.target.value;
          if (v === NEW) {
            const n = window.prompt("Nome da nova personagem");
            if (n?.trim()) onChange({ ...l, kind: "dialogue", character: n.trim().toUpperCase() });
          } else onChange({ ...l, kind: v ? "dialogue" : "direction", character: v || null });
        }}
        className="h-9 rounded-lg bg-[#0A0908] border border-white/10 px-3 text-xs font-mono tracking-widest text-sky-300"
      >
        <option value="">— RUBRICA —</option>
        {names.map((n) => <option key={n} value={n}>{n}</option>)}
        <option value={NEW}>+ nova personagem…</option>
      </select>
      <div className="ml-auto flex gap-1">
        <button data-testid={`edit-line-insert-${i}`} onClick={onInsert} title="Inserir fala abaixo"
          className="h-8 w-8 rounded-full flex items-center justify-center text-stone-400 hover:text-amber-400 hover:bg-white/5"><Plus className="w-4 h-4" /></button>
        <button data-testid={`edit-line-delete-${i}`} onClick={onRemove} title="Apagar"
          className="h-8 w-8 rounded-full flex items-center justify-center text-stone-400 hover:text-rose-400 hover:bg-white/5"><Trash2 className="w-4 h-4" /></button>
      </div>
    </div>
    <Textarea data-testid={`edit-line-text-${i}`} value={l.text} onChange={(e) => onChange({ ...l, text: e.target.value })}
      className={`bg-[#0A0908] min-h-[60px] ${l.kind === "direction" ? "italic text-stone-400" : ""}`} />
    {l.edited_text && (
      <p className="text-xs text-emerald-300/90" data-testid={`edit-line-memory-hint-${i}`}>
        <span className="font-mono tracking-widest mr-2">ALTERADO POR NOTA DA MEMÓRIA:</span>"{l.edited_text}" (apaga a nota na Memória para usar este texto)
      </p>
    )}
  </div>
);

export const ScriptEditor = ({ script, onSaved, onCancel }) => {
  const [lines, setLines] = useState(() => script.lines.map(({ uid, character, text, kind, edited_text }) => ({ uid, character, text, kind, edited_text, key: uid })));
  const [busy, setBusy] = useState(false);
  const names = [...new Set([...script.characters.map((c) => c.name), ...lines.filter((l) => l.character).map((l) => l.character)])];

  const set = (i, v) => setLines((ls) => ls.map((x, k) => (k === i ? v : x)));
  const remove = (i) => setLines((ls) => ls.filter((_, k) => k !== i));
  const insert = (i) => setLines((ls) => [...ls.slice(0, i + 1), { character: ls[i]?.character || names[0], text: "", kind: "dialogue", key: Math.random().toString(36).slice(2) }, ...ls.slice(i + 1)]);

  const save = async () => {
    setBusy(true);
    try {
      onSaved(await api.updateLines(script.id, lines));
      toast.success("Guião actualizado");
    } catch (e) {
      toast.error(errMsg(e));
    }
    setBusy(false);
  };

  return (
    <div className="space-y-3" data-testid="script-editor">
      <div className="sticky top-16 z-20 flex items-center justify-between gap-3 py-3 bg-[#0A0908]/90 backdrop-blur">
        <p className="text-sm text-stone-400">Edita falas, muda a personagem, transforma em rubrica, insere ou apaga.</p>
        <div className="flex gap-2">
          <Button data-testid="editor-cancel-btn" variant="outline" onClick={onCancel} className="rounded-full"><X className="w-4 h-4 mr-1" />Cancelar</Button>
          <Button data-testid="editor-save-btn" onClick={save} disabled={busy} className="rounded-full">
            {busy ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}Guardar
          </Button>
        </div>
      </div>
      {lines.map((l, i) => (
        <LineRow key={l.key} l={l} i={i} names={names} onChange={(v) => set(i, v)} onRemove={() => remove(i)} onInsert={() => insert(i)} />
      ))}
      <Button data-testid="editor-add-line-btn" variant="outline" className="rounded-full" onClick={() => insert(lines.length - 1)}>
        <Plus className="w-4 h-4 mr-1" /> Adicionar fala no fim
      </Button>
    </div>
  );
};
