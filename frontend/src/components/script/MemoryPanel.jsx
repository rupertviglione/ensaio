import { useState } from "react";
import { BookmarkPlus, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, errMsg, fmtDate } from "@/lib/api";

export const MemoryPanel = ({ script, onReload }) => {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const add = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const note = await api.addMemory(script.id, text);
      await onReload();
      setText("");
      toast.success(note.new_text ? "Guardado e aplicado no guião" : "Guardado na memória do texto");
    } catch (e) {
      toast.error(errMsg(e));
    }
    setBusy(false);
  };
  const remove = async (id) => {
    await api.deleteMemory(script.id, id);
    await onReload();
  };
  const lineOf = (uid) => script.lines.find((l) => l.uid === uid);
  return (
    <div className="space-y-6">
      <p className="text-sm text-stone-400">
        Alterações acordadas nos ensaios. A IA passa a considerá-las como o texto correcto. Também podes dizê-las em voz alta durante o ensaio
        (ex.: <em className="text-stone-300">"aí mudámos, agora digo X em vez de Y"</em>) e ficam guardadas aqui.
      </p>
      <div className="rounded-xl border border-white/[0.07] bg-[#141210] p-4">
        <Textarea data-testid="memory-input" value={text} onChange={(e) => setText(e.target.value)}
          placeholder='Ex.: Na fala do JOÃO "E hoje é dia de pedra", a MARTA responde "Hoje é mesmo dia de pedra".'
          className="bg-[#0A0908] min-h-[90px]" />
        <Button data-testid="memory-add-btn" onClick={add} disabled={busy} className="mt-3 rounded-full">
          {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <BookmarkPlus className="w-4 h-4 mr-2" />}Guardar nota
        </Button>
      </div>
      {script.memory.length === 0 ? (
        <p className="text-sm text-stone-500" data-testid="memory-empty">Ainda não há notas para este texto.</p>
      ) : (
        <ul className="space-y-3" data-testid="memory-list">
          {script.memory.map((m) => (
            <li key={m.id} data-testid={`memory-note-${m.id}`} className="flex gap-4 items-start rounded-xl border-l-2 border-emerald-500/60 bg-emerald-500/[0.04] px-5 py-4">
              <div className="flex-1">
                <p className="text-stone-200">{m.text}</p>
                {m.new_text && lineOf(m.line_uid) && (
                  <p data-testid={`memory-note-applied-${m.id}`} className="text-xs text-emerald-300/90 mt-2">
                    <span className="font-mono tracking-widest mr-2">APLICADO EM {lineOf(m.line_uid).character}:</span>"{m.new_text}"
                  </p>
                )}
                <p className="text-[11px] font-mono text-stone-500 mt-2">{fmtDate(m.created_at)}</p>
              </div>
              <button data-testid={`memory-delete-btn-${m.id}`} onClick={() => remove(m.id)} className="text-stone-500 hover:text-rose-400 transition-colors">
                <Trash2 className="w-4 h-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
