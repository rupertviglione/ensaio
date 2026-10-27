import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mic, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg } from "@/lib/api";

const PRESETS = [
  { id: "grave", label: "Só erros graves", text: "Interrompe apenas se houver algum erro grave ou um salto grande. Deixa passar pequenas trocas, enganos e repetições." },
  { id: "rigor", label: "Rigoroso", text: "Modo rigoroso: interrompe quando eu trocar, saltar ou acrescentar palavras. Ignora pronúncia, formas coloquiais (prá, tá…) e pequenas falhas de reconhecimento." },
  { id: "nunca", label: "Nunca interromper", text: "Nunca me interrompas. Deixa tudo para o resumo final." },
];

export const prefsKey = (id) => `ensaio-prefs-${id}`;
export const loadPrefs = (id) => JSON.parse(localStorage.getItem(prefsKey(id)) || "{}");

export const RehearsalSetup = ({ script, startIdx, onStartIdx }) => {
  const nav = useNavigate();
  const saved = loadPrefs(script.id);
  const [character, setCharacter] = useState(saved.character || "");
  const [instructions, setInstructions] = useState(saved.instructions ?? PRESETS[0].text);
  const [hideText, setHideText] = useState(saved.hideText ?? true);
  const [hintSeconds, setHintSeconds] = useState(saved.hintSeconds ?? 5);
  const [busy, setBusy] = useState(false);

  const start = async () => {
    if (!character) return toast.error("Escolhe primeiro o teu papel.");
    const hs = Number(hintSeconds);
    if (!Number.isInteger(hs) || hs < 3 || hs > 15) return toast.error("O tempo até à dica tem de ser entre 3 e 15 segundos.");
    setBusy(true);
    localStorage.setItem(prefsKey(script.id), JSON.stringify({ character, instructions, hideText, hintSeconds: hs }));
    try {
      const strictness = PRESETS.find((p) => p.text === instructions)?.id || "grave";
      const s = await api.createSession({ script_id: script.id, character, instructions, strictness, start_idx: startIdx, hint_seconds: hs });
      nav(`/ensaio/${s.id}`);
    } catch (e) {
      toast.error(errMsg(e));
      setBusy(false);
    }
  };

  const startLine = script.lines[startIdx];
  return (
    <div className="rounded-2xl border border-amber-500/20 bg-[#141210] p-6 space-y-6" data-testid="rehearsal-setup">
      <h2 className="font-serif text-2xl font-semibold">Preparar ensaio</h2>
      <div>
        <label className="text-xs font-mono tracking-widest text-stone-500">O MEU PAPEL</label>
        <Select value={character} onValueChange={setCharacter}>
          <SelectTrigger data-testid="character-select" className="mt-2 h-11 bg-[#0A0908]"><SelectValue placeholder="Escolhe a tua personagem" /></SelectTrigger>
          <SelectContent>
            {script.characters.map((c) => <SelectItem key={c.name} value={c.name} data-testid={`character-option-${c.name}`}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div>
        <label className="text-xs font-mono tracking-widest text-stone-500">COMO QUERES QUE TE CORRIJA</label>
        <div className="flex flex-wrap gap-2 mt-2">
          {PRESETS.map((p) => (
            <button key={p.id} data-testid={`preset-${p.id}`} onClick={() => setInstructions(p.text)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${instructions === p.text ? "border-amber-500 text-amber-400 bg-amber-500/10" : "border-white/10 text-stone-400 hover:text-stone-100"}`}>
              {p.label}
            </button>
          ))}
        </div>
        <Textarea data-testid="instructions-input" value={instructions} onChange={(e) => setInstructions(e.target.value)} className="mt-3 bg-[#0A0908] min-h-[110px] text-sm" />
      </div>
      <div className="flex items-center justify-between">
        <label htmlFor="hide" className="text-sm text-stone-300">Esconder o meu texto</label>
        <Switch id="hide" data-testid="hide-text-switch" checked={hideText} onCheckedChange={setHideText} />
      </div>
      <div className="flex items-center justify-between gap-4">
        <label htmlFor="hint-seconds" className="text-sm text-stone-300">
          Dica após silêncio <span className="text-stone-500 text-xs">(3–15 s)</span>
        </label>
        <div className="flex items-center gap-2">
          <Input id="hint-seconds" data-testid="hint-seconds-input" type="number" min={3} max={15} step={1} value={hintSeconds}
            onChange={(e) => setHintSeconds(e.target.value)} className="w-20 h-9 bg-[#0A0908] text-center" />
          <span className="text-xs text-stone-500">s</span>
        </div>
      </div>
      <div className="text-xs text-stone-500 flex items-center justify-between gap-2">
        <span>Começa em: <span className="text-stone-300">{startIdx === 0 ? "início" : `${startLine?.character || "rubrica"} — "${(startLine?.text || "").slice(0, 30)}…"`}</span></span>
        {startIdx !== 0 && <button data-testid="reset-start-btn" className="text-amber-400 hover:underline" onClick={() => onStartIdx(0)}>início</button>}
      </div>
      <Button data-testid="start-rehearsal-button" onClick={start} disabled={busy} size="lg" className="w-full h-12 rounded-full font-semibold">
        {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Mic className="w-4 h-4 mr-2" />} Começar ensaio
      </Button>
    </div>
  );
};
