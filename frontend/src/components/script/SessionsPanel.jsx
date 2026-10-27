import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { fmtDate } from "@/lib/api";

export const SessionsPanel = ({ sessions }) =>
  sessions.length === 0 ? (
    <p className="text-sm text-stone-500" data-testid="sessions-empty">Ainda não ensaiaste este texto.</p>
  ) : (
    <ul className="space-y-3" data-testid="sessions-list">
      {sessions.map((s) => (
        <li key={s.id}>
          <Link
            to={s.status === "finished" ? `/resumo/${s.id}` : `/ensaio/${s.id}`}
            data-testid={`session-link-${s.id}`}
            className="flex items-center gap-5 rounded-xl border border-white/[0.07] bg-[#141210] px-5 py-4 hover:border-amber-500/40 transition-colors"
          >
            <span className="font-serif text-3xl w-16 text-amber-400">
              {s.summary?.score != null ? `${Math.round(s.summary.score)}%` : "—"}
            </span>
            <div className="flex-1">
              <p className="text-stone-200 font-medium">{s.character}</p>
              <p className="text-xs text-stone-500 font-mono mt-1">
                {fmtDate(s.created_at)} · {s.status === "finished" ? "TERMINADO" : "EM CURSO"}
              </p>
            </div>
            <ChevronRight className="w-4 h-4 text-stone-500" />
          </Link>
        </li>
      ))}
    </ul>
  );
