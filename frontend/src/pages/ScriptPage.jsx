import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ScriptEditor } from "@/components/script/ScriptEditor";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { ScriptView } from "@/components/script/ScriptView";
import { CharactersPanel } from "@/components/script/CharactersPanel";
import { MemoryPanel } from "@/components/script/MemoryPanel";
import { SessionsPanel } from "@/components/script/SessionsPanel";
import { RehearsalSetup } from "@/components/script/RehearsalSetup";

const tabCls = "rounded-full px-4 data-[state=active]:bg-amber-500/15 data-[state=active]:text-amber-400";

export default function ScriptPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [script, setScript] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [startIdx, setStartIdx] = useState(0);
  const [editing, setEditing] = useState(false);
  const reload = () => api.getScript(id).then(setScript);

  useEffect(() => {
    api.getScript(id).then(setScript).catch(() => nav("/"));
    api.scriptSessions(id).then(setSessions).catch(() => {});
  }, [id, nav]);

  const remove = async () => {
    if (!window.confirm("Apagar este texto e todos os ensaios?")) return;
    await api.deleteScript(id);
    toast.success("Texto apagado");
    nav("/");
  };

  if (!script) return <div className="max-w-7xl mx-auto px-10 py-20"><Skeleton className="h-96 bg-white/5 rounded-2xl" /></div>;

  return (
    <div className="max-w-7xl mx-auto px-6 md:px-10 py-12 md:py-16">
      <div className="flex items-start justify-between gap-6 mb-10 rise">
        <div>
          <p className="font-mono text-xs tracking-[0.3em] text-amber-500 mb-3">{(script.author || "Texto").toUpperCase()}</p>
          <h1 data-testid="script-title" className="font-serif text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">{script.title}</h1>
          <p className="text-stone-400 mt-3 text-sm">{script.characters.map((c) => c.name).join(" · ")}</p>
        </div>
        <button data-testid="delete-script-btn" onClick={remove} className="text-stone-500 hover:text-rose-400 transition-colors p-2" title="Apagar">
          <Trash2 className="w-5 h-5" />
        </button>
      </div>

      <div className="grid lg:grid-cols-[1fr_380px] gap-10 items-start">
        <Tabs defaultValue="guiao">
          <TabsList className="bg-[#141210] rounded-full p-1 h-auto mb-8">
            <TabsTrigger value="guiao" className={tabCls} data-testid="tab-script">Guião</TabsTrigger>
            <TabsTrigger value="vozes" className={tabCls} data-testid="tab-voices">Vozes</TabsTrigger>
            <TabsTrigger value="memoria" className={tabCls} data-testid="tab-memory">Memória ({script.memory.length})</TabsTrigger>
            <TabsTrigger value="ensaios" className={tabCls} data-testid="tab-sessions">Ensaios ({sessions.length})</TabsTrigger>
          </TabsList>
          <TabsContent value="guiao">
            {editing ? (
              <ScriptEditor script={script} onCancel={() => setEditing(false)} onSaved={(s) => { setScript(s); setEditing(false); setStartIdx(0); }} />
            ) : (
              <>
                <div className="flex justify-end mb-3">
                  <Button data-testid="edit-script-btn" variant="outline" size="sm" className="rounded-full" onClick={() => setEditing(true)}>
                    <Pencil className="w-4 h-4 mr-2" /> Editar falas e personagens
                  </Button>
                </div>
                <ScriptView lines={script.lines} startIdx={startIdx} onStartHere={setStartIdx} />
              </>
            )}
          </TabsContent>
          <TabsContent value="vozes"><CharactersPanel script={script} onSaved={setScript} /></TabsContent>
          <TabsContent value="memoria"><MemoryPanel script={script} onReload={reload} /></TabsContent>
          <TabsContent value="ensaios"><SessionsPanel sessions={sessions} /></TabsContent>
        </Tabs>
        <div className="lg:sticky lg:top-24">
          <RehearsalSetup script={script} startIdx={startIdx} onStartIdx={setStartIdx} />
        </div>
      </div>
    </div>
  );
}
