import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Users, MessageSquareQuote, CalendarClock, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fmtDate } from "@/lib/api";

const ScriptCard = ({ s, i }) => (
  <Link
    to={`/texto/${s.id}`}
    data-testid={`script-card-${s.id}`}
    style={{ animationDelay: `${i * 70}ms` }}
    className="rise group relative block rounded-2xl border border-white/[0.07] bg-[#141210] p-7 transition-[border-color,transform,background-color] duration-300 hover:-translate-y-1 hover:border-amber-500/40 hover:bg-[#1C1917]"
  >
    <ArrowUpRight className="absolute top-6 right-6 w-5 h-5 text-stone-600 transition-colors group-hover:text-amber-400" />
    <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-stone-500">{s.author || "Texto"}</p>
    <h3 className="font-serif text-3xl font-semibold text-stone-100 mt-2 pr-8 leading-tight">{s.title}</h3>
    <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-xs text-stone-400">
      <span className="flex items-center gap-1.5"><Users className="w-3.5 h-3.5" />{s.characters.length} personagens</span>
      <span className="flex items-center gap-1.5"><MessageSquareQuote className="w-3.5 h-3.5" />{s.line_count} falas</span>
      <span className="flex items-center gap-1.5"><CalendarClock className="w-3.5 h-3.5" />{fmtDate(s.last_rehearsal)}</span>
    </div>
    {s.last_score != null && (
      <div className="mt-5">
        <div className="flex justify-between text-[11px] font-mono text-stone-500 mb-1.5">
          <span>ÚLTIMO ENSAIO</span><span className="text-amber-400">{Math.round(s.last_score)}%</span>
        </div>
        <div className="h-1 rounded-full bg-white/5 overflow-hidden">
          <div className="h-full bg-amber-500" style={{ width: `${s.last_score}%` }} />
        </div>
      </div>
    )}
  </Link>
);

export default function Library() {
  const [scripts, setScripts] = useState(null);
  useEffect(() => { api.listScripts().then(setScripts).catch(() => setScripts([])); }, []);

  return (
    <div className="max-w-7xl mx-auto px-6 md:px-10 py-14 md:py-20">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 mb-14">
        <div className="rise">
          <p className="font-mono text-xs tracking-[0.3em] text-amber-500 mb-4">BIBLIOTECA DE TEXTOS</p>
          <h1 className="font-serif text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-stone-100">
            O que vamos <em className="text-amber-400 font-normal">ensaiar</em> hoje?
          </h1>
          <p className="text-stone-400 mt-4 max-w-xl text-sm md:text-base">
            Escolhe um texto, diz qual é o teu papel, e a IA dá voz a todas as outras personagens enquanto te acompanha fala a fala.
          </p>
        </div>
        <Button asChild size="lg" className="rounded-full h-12 px-7 font-semibold" data-testid="library-new-script-btn">
          <Link to="/novo"><Plus className="w-4 h-4 mr-1" /> Carregar texto</Link>
        </Button>
      </div>

      {scripts === null ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[0, 1, 2].map((k) => <Skeleton key={k} className="h-52 rounded-2xl bg-white/5" />)}
        </div>
      ) : scripts.length === 0 ? (
        <div data-testid="library-empty" className="rounded-2xl border border-dashed border-white/10 p-16 text-center text-stone-400">
          Ainda não tens textos. Carrega o primeiro para começar.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="library-grid">
          {scripts.map((s, i) => <ScriptCard key={s.id} s={s} i={i} />)}
        </div>
      )}
    </div>
  );
}
