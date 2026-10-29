import { useEffect, useState } from "react";
import { Loader2, Plus, Trash2, Wand2, Save, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api, errMsg, voiceBody } from "@/lib/api";
import { playUrl } from "@/lib/audio";

const LANGS = { fr: "Francês", en: "Inglês", it: "Italiano", de: "Alemão", es: "Espanhol", la: "Latim", ru: "Russo", pt: "Português" };
const blank = { text: "", lang: "fr", say: "", variants: [] };

const Row = ({ it, k, onChange, onRemove, onPreview }) => (
  <div data-testid={`pron-row-${k}`} className="grid md:grid-cols-[1.2fr_130px_1.2fr_1.4fr_auto] gap-2 items-center rounded-xl border border-white/[0.07] bg-[#141210] p-3">
    <Input data-testid={`pron-text-${k}`} value={it.text} onChange={(e) => onChange({ ...it, text: e.target.value })} placeholder="Como está no texto" className="bg-[#0A0908]" />
    <select data-testid={`pron-lang-${k}`} value={it.lang} onChange={(e) => onChange({ ...it, lang: e.target.value })} className="h-10 rounded-md bg-[#0A0908] border border-white/10 px-2 text-sm text-stone-300">
      {Object.entries(LANGS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
      {!LANGS[it.lang] && it.lang && <option value={it.lang}>{it.lang}</option>}
    </select>
    <Input data-testid={`pron-say-${k}`} value={it.say} onChange={(e) => onChange({ ...it, say: e.target.value })} placeholder="Como a voz deve dizer" className="bg-[#0A0908]" />
    <Input data-testid={`pron-variants-${k}`} value={(it.variants || []).join(", ")} onChange={(e) => onChange({ ...it, variants: e.target.value.split(",").map((v) => v.trim()).filter(Boolean) })}
      placeholder="Como a escuta pode ouvir (separado por vírgulas)" className="bg-[#0A0908] text-xs" />
    <div className="flex gap-1">
      <button data-testid={`pron-preview-${k}`} onClick={onPreview} title="Ouvir" className="h-9 w-9 rounded-full border border-white/10 flex items-center justify-center text-stone-300 hover:text-amber-400"><Volume2 className="w-4 h-4" /></button>
      <button data-testid={`pron-remove-${k}`} onClick={onRemove} title="Remover" className="h-9 w-9 rounded-full border border-white/10 flex items-center justify-center text-stone-400 hover:text-rose-400"><Trash2 className="w-4 h-4" /></button>
    </div>
  </div>
);

export const PronunciationPanel = ({ script }) => {
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState("");
  useEffect(() => { api.pronunciation(script.id).then((r) => setItems(r.items)).catch((e) => toast.error(errMsg(e))); }, [script.id]);
  const set = (k, v) => setItems((xs) => xs.map((x, i) => (i === k ? v : x)));
  const act = async (name, fn, ok) => {
    setBusy(name);
    try { const r = await fn(); setItems(r.items); toast.success(ok); } catch (e) { toast.error(errMsg(e)); }
    setBusy("");
  };
  const preview = async (it) => {
    const c = script.characters[0];
    try {
      await api.savePronunciation(script.id, items);
      await playUrl(await api.tts({ text: it.text, ...voiceBody(c, script.id) }));
    } catch (e) { toast.error(errMsg(e)); }
  };
  if (!items) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-amber-500" /></div>;
  return (
    <div className="space-y-4" data-testid="pronunciation-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-stone-400 max-w-xl">Palavras e nomes estrangeiros. As vozes dizem-nos como escreveres em "Como a voz deve dizer"; a escuta reconhece-os e aceita as variantes.</p>
        <div className="flex gap-2">
          <Button data-testid="pron-detect-btn" variant="outline" size="sm" className="rounded-full" disabled={!!busy}
            onClick={() => act("detect", () => api.detectPronunciation(script.id), "Palavras estrangeiras detectadas")}>
            {busy === "detect" ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Wand2 className="w-4 h-4 mr-2" />} Detectar de novo
          </Button>
          <Button data-testid="pron-add-btn" variant="outline" size="sm" className="rounded-full" onClick={() => setItems((xs) => [...xs, { ...blank }])}><Plus className="w-4 h-4 mr-2" /> Acrescentar</Button>
          <Button data-testid="pron-save-btn" size="sm" className="rounded-full" disabled={!!busy}
            onClick={() => act("save", () => api.savePronunciation(script.id, items), "Pronúncia guardada")}>
            {busy === "save" ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />} Guardar
          </Button>
        </div>
      </div>
      {items.length === 0 && <p className="text-stone-500 text-sm" data-testid="pron-empty">Nenhuma palavra estrangeira detectada.</p>}
      {items.map((it, k) => <Row key={k} k={k} it={it} onChange={(v) => set(k, v)} onRemove={() => setItems((xs) => xs.filter((_, i) => i !== k))} onPreview={() => preview(it)} />)}
    </div>
  );
};
