import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileUp, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, errMsg } from "@/lib/api";

const DropZone = ({ onText }) => {
  const ref = useRef();
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const handle = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const r = await api.extract(file);
      onText(r.text, file.name.replace(/\.[^.]+$/, ""));
      toast.success("Texto extraído do ficheiro");
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div
      data-testid="upload-dropzone"
      onClick={() => ref.current.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); handle(e.dataTransfer.files[0]); }}
      className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-colors duration-200 ${
        over ? "border-amber-500 bg-amber-500/5" : "border-white/10 hover:border-amber-500/50 bg-[#141210]"
      }`}
    >
      <input ref={ref} type="file" accept=".pdf,.docx,.txt,.md" className="hidden" data-testid="upload-file-input"
        onChange={(e) => handle(e.target.files[0])} />
      {busy ? <Loader2 className="w-8 h-8 mx-auto text-amber-500 animate-spin" /> : <FileUp className="w-8 h-8 mx-auto text-amber-500" />}
      <p className="mt-4 text-stone-200 font-medium">Larga aqui um ficheiro ou clica para escolher</p>
      <p className="mt-1 text-xs text-stone-500 font-mono">PDF · WORD (.DOCX) · TXT</p>
    </div>
  );
};

export default function NewScript() {
  const nav = useNavigate();
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!text.trim()) return toast.error("Cola ou carrega um texto primeiro.");
    setSaving(true);
    try {
      const s = await api.createScript({ title: title || "Sem título", author, text });
      toast.success(`${s.characters.length} personagens e ${s.lines.filter((l) => l.kind === "dialogue").length} falas identificadas`);
      nav(`/texto/${s.id}`);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-6 md:px-10 py-14 md:py-20">
      <p className="font-mono text-xs tracking-[0.3em] text-amber-500 mb-4 rise">NOVO TEXTO</p>
      <h1 className="font-serif text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight rise">Carregar texto</h1>
      <p className="text-stone-400 mt-4 max-w-2xl text-sm md:text-base rise">
        Cola o texto ou carrega um ficheiro. Funciona melhor com o formato <span className="font-mono text-amber-400">NOME: fala</span> ou com o nome da personagem numa linha e a fala por baixo. Rubricas entre parêntesis são reconhecidas.
      </p>

      <div className="mt-12 grid md:grid-cols-[1fr_1.4fr] gap-8">
        <div className="space-y-5">
          <div>
            <label className="text-xs font-mono tracking-widest text-stone-500">TÍTULO</label>
            <Input data-testid="new-script-title-input" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="Ex.: Frei Luís de Sousa — Acto I" className="mt-2 h-12 bg-[#141210]" />
          </div>
          <div>
            <label className="text-xs font-mono tracking-widest text-stone-500">AUTOR / NOTA</label>
            <Input data-testid="new-script-author-input" value={author} onChange={(e) => setAuthor(e.target.value)}
              placeholder="Opcional" className="mt-2 h-12 bg-[#141210]" />
          </div>
          <DropZone onText={(t, name) => { setText(t); if (!title) setTitle(name); }} />
        </div>
        <div className="flex flex-col">
          <label className="text-xs font-mono tracking-widest text-stone-500">TEXTO</label>
          <Textarea data-testid="new-script-text-input" value={text} onChange={(e) => setText(e.target.value)}
            placeholder={"JOÃO: Ainda estás aqui?\nMARTA: Perdi o comboio.\n(Pausa.)\nJOÃO: Porquê?"}
            className="mt-2 flex-1 min-h-[360px] font-mono text-sm leading-relaxed bg-[#141210]" />
          <Button data-testid="new-script-save-btn" onClick={save} disabled={saving} size="lg" className="mt-5 h-12 rounded-full font-semibold self-end px-8">
            {saving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> A identificar personagens…</> : <><Sparkles className="w-4 h-4 mr-2" /> Preparar texto</>}
          </Button>
        </div>
      </div>
    </div>
  );
}
