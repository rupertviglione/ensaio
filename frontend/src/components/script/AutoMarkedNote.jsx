import { X } from "lucide-react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";

export const AutoMarkedNote = ({ script, onSaved }) => {
  const ids = (script.auto_marked || []).filter((u) => script.lines.some((l) => l.uid === u && l.kind === "foreign"));
  if (!ids.length || script.auto_marked_dismissed) return null;
  const first = script.lines.find((l) => l.uid === ids[0]);
  const review = () => document.querySelector(`[data-testid="script-line-${first.idx}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  const dismiss = async () => { try { onSaved(await api.dismissAutoMarked(script.id)); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div data-testid="auto-marked-note" className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-sky-500/30 bg-sky-500/[0.06] px-4 py-3 text-sm text-sky-200">
      <span>
        <span data-testid="auto-marked-count">{ids.length}</span> {ids.length === 1 ? "linha marcada" : "linhas marcadas"} como texto não pertencente (números de página, cabeçalhos) —{" "}
        <button data-testid="auto-marked-review-btn" onClick={review} className="underline underline-offset-4 hover:text-sky-100">rever</button>
      </span>
      <button data-testid="auto-marked-dismiss-btn" onClick={dismiss} title="Dispensar" className="text-sky-300 hover:text-sky-100"><X className="w-4 h-4" /></button>
    </div>
  );
};
