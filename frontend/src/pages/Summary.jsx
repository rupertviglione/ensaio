import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Loader2, BookmarkPlus, RotateCcw, Check, Target } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, errMsg, fmtDate } from "@/lib/api";

const Block = ({ title, children, testid }) => (
  <section data-testid={testid} className="rise rounded-2xl border border-white/[0.07] bg-[#141210] p-7">
    <h2 className="font-mono text-xs tracking-[0.3em] text-amber-500 mb-5">{title}</h2>
    {children}
  </section>
);

const Stat = ({ label, value }) => (
  <div>
    <p className="font-serif text-4xl text-stone-100">{value ?? "—"}</p>
    <p className="text-[11px] font-mono tracking-widest text-stone-500 mt-1">{label}</p>
  </div>
);

const applyEdit = (line, d) => {
  if (!line || !d.expected) return null;
  const base = line.edited_text || line.text;
  const pos = base.toLowerCase().indexOf(d.expected.toLowerCase());
  return pos < 0 ? null : base.slice(0, pos) + (d.said || "") + base.slice(pos + d.expected.length);
};

const DiffRow = ({ d, script, i, onSaved }) => {
  const [saved, setSaved] = useState(false);
  const save = async () => {
    try {
      const newText = applyEdit(script.lines[d.line_idx], d);
      await api.addMemory(script.id, `Alteração acordada: em vez de "${d.expected}", o actor diz "${d.said}".`,
        { line_idx: d.line_idx ?? null, new_text: newText ? newText.replace(/\s+/g, " ").trim() : null });
      setSaved(true);
      onSaved();
      toast.success("Guardado como alteração acordada");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <li data-testid={`diff-row-${i}`} className="grid md:grid-cols-[110px_1fr_1fr_auto] gap-3 md:gap-5 items-start py-4 border-b border-white/[0.05] last:border-0">
      <span className="font-mono text-[11px] uppercase tracking-widest text-amber-400 pt-1">{d.type}</span>
      <p className="text-emerald-300/90"><span className="text-stone-500 text-xs block font-mono">TEXTO</span>"{d.expected}"</p>
      <div>
        <p className="text-rose-300/90"><span className="text-stone-500 text-xs block font-mono">DISSESTE</span>"{d.said || "—"}"</p>
        {d.note && <p className="text-xs text-stone-500 mt-1">{d.note}</p>}
      </div>
      <button data-testid={`diff-save-memory-btn-${i}`} onClick={save} disabled={saved} title="Isto foi mudado nos ensaios — guardar na memória"
        className="text-xs flex items-center gap-1 text-stone-400 hover:text-emerald-300 disabled:text-emerald-400 transition-colors whitespace-nowrap">
        {saved ? <Check className="w-4 h-4" /> : <BookmarkPlus className="w-4 h-4" />} {saved ? "Guardado" : "É alteração acordada"}
      </button>
    </li>
  );
};

export default function Summary() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [session, setSession] = useState(null);
  const [script, setScript] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        let s = await api.getSession(sessionId);
        if (s.status !== "finished") s = await api.finish(sessionId);
        setSession(s);
        setScript(await api.getScript(s.script_id));
      } catch (e) {
        setError(errMsg(e));
      }
    })();
  }, [sessionId]);

  if (error) return <p className="text-center py-24 text-rose-300" data-testid="summary-error">{error}</p>;
  if (!session || !script)
    return (
      <div className="flex flex-col items-center py-32 gap-4 text-stone-400" data-testid="summary-loading">
        <Loader2 className="w-8 h-8 animate-spin text-amber-500" /> A analisar a tua prestação…
      </div>
    );

  const sm = session.summary || {};
  const st = sm.stats || {};
  const lineText = (i) => script.lines[i]?.edited_text || script.lines[i]?.text;
  const focusIdxs = [...new Set([...(sm.zones_to_review || []), ...(sm.differences || [])]
    .map((z) => z.line_idx)
    .filter((i) => Number.isInteger(i) && script.lines[i]?.character === session.character))].sort((a, b) => a - b);
  const rehearseZones = async () => {
    try {
      const s = await api.createSession({
        script_id: script.id, character: session.character, instructions: session.instructions,
        strictness: session.strictness || "grave", start_idx: focusIdxs[0], focus_idxs: focusIdxs,
      });
      nav(`/ensaio/${s.id}`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 md:px-10 py-14 space-y-8">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 rise">
        <div>
          <p className="font-mono text-xs tracking-[0.3em] text-amber-500 mb-3">RESUMO DA PRESTAÇÃO · {fmtDate(session.finished_at)}</p>
          <h1 className="font-serif text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">{script.title}</h1>
          <p className="text-stone-400 mt-2">Papel: <span className="text-stone-200">{session.character}</span></p>
        </div>
        <div className="flex flex-wrap gap-3">
          {focusIdxs.length > 0 && (
            <Button data-testid="rehearse-zones-btn" onClick={rehearseZones} variant="outline" className="rounded-full h-11 px-6 border-rose-500/40 text-rose-200 hover:bg-rose-500/10">
              <Target className="w-4 h-4 mr-2" /> Ensaiar zonas a rever ({focusIdxs.length})
            </Button>
          )}
          <Button asChild className="rounded-full h-11 px-6" data-testid="rehearse-again-btn">
            <Link to={`/texto/${script.id}`}><RotateCcw className="w-4 h-4 mr-2" /> Ensaiar outra vez</Link>
          </Button>
        </div>
      </div>

      <div className="grid md:grid-cols-[280px_1fr] gap-8">
        <div className="rise rounded-2xl border border-amber-500/30 bg-amber-500/[0.06] p-8 flex flex-col justify-center">
          <p data-testid="summary-score" className="font-serif text-7xl font-bold text-amber-400">{sm.score != null ? `${Math.round(sm.score)}%` : "—"}</p>
          <p className="font-mono text-[11px] tracking-widest text-stone-400 mt-2">FIDELIDADE AO TEXTO</p>
        </div>
        <Block title="SÍNTESE" testid="summary-overview">
          <p className="text-stone-200 leading-relaxed">{sm.overview}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mt-7">
            <Stat label="FALAS DITAS" value={st.lines_attempted} />
            <Stat label="TENTATIVAS" value={st.attempts} />
            <Stat label="INTERRUPÇÕES" value={st.interruptions} />
            <Stat label="PRECISÃO MÉDIA" value={st.avg_accuracy != null ? `${st.avg_accuracy}%` : null} />
          </div>
        </Block>
      </div>

      <Block title={`TUDO O QUE FOI DIFERENTE DO TEXTO (${sm.differences?.length || 0})`} testid="summary-differences">
        {sm.differences?.length ? (
          <ul>{sm.differences.map((d, i) => <DiffRow key={i} d={d} i={i} script={script} onSaved={() => api.getScript(script.id).then(setScript)} />)}</ul>
        ) : <p className="text-stone-400">Nenhuma diferença. Texto dito tal e qual.</p>}
      </Block>

      <div className="grid md:grid-cols-2 gap-8">
        <Block title="ZONAS A REVER" testid="summary-zones">
          <ul className="space-y-4">
            {(sm.zones_to_review || []).map((z, i) => (
              <li key={i} className="border-l-2 border-rose-500/50 pl-4">
                {lineText(z.line_idx) && <p className="font-serif italic text-stone-300">"{lineText(z.line_idx)}"</p>}
                <p className="text-sm text-stone-400 mt-1">{z.reason}</p>
              </li>
            ))}
            {!sm.zones_to_review?.length && <p className="text-stone-500 text-sm">Sem zonas críticas.</p>}
          </ul>
        </Block>
        <Block title="AJUDA PARA MEMORIZAR" testid="summary-tips">
          <ul className="space-y-3 list-disc pl-5 text-stone-300">
            {(sm.memorization_tips || []).map((t, i) => <li key={i}>{t}</li>)}
          </ul>
          {sm.strengths?.length > 0 && (
            <>
              <h3 className="font-mono text-[11px] tracking-widest text-emerald-400 mt-7 mb-3">PONTOS FORTES</h3>
              <ul className="space-y-2 list-disc pl-5 text-stone-400 text-sm">{sm.strengths.map((t, i) => <li key={i}>{t}</li>)}</ul>
            </>
          )}
          {sm.next_steps && <p className="mt-6 text-sm text-amber-200/90 border-t border-white/5 pt-4">{sm.next_steps}</p>}
        </Block>
      </div>
    </div>
  );
}
