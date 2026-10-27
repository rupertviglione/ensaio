import { useState } from "react";
import { Volume2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg, VOICES } from "@/lib/api";
import { playUrl } from "@/lib/audio";

const CharacterRow = ({ c, sample, onChange }) => {
  const [busy, setBusy] = useState(false);
  const preview = async () => {
    setBusy(true);
    try {
      const url = await api.tts({ text: sample, voice: c.voice, character: c.name, style: c.style });
      setBusy(false);
      await playUrl(url);
    } catch (e) {
      toast.error(errMsg(e));
      setBusy(false);
    }
  };
  return (
    <div className="rounded-xl border border-white/[0.07] bg-[#141210] p-5 grid md:grid-cols-[1fr_220px_auto] gap-4 items-end" data-testid={`character-row-${c.name}`}>
      <div>
        <p className="font-mono text-sm tracking-widest font-bold text-sky-300">{c.name}</p>
        <Input
          data-testid={`character-style-input-${c.name}`}
          defaultValue={c.style}
          onBlur={(e) => e.target.value !== c.style && onChange({ ...c, style: e.target.value })}
          placeholder="Carácter da voz (ex.: velho, irónico, fala devagar)"
          className="mt-3 bg-[#0A0908]"
        />
      </div>
      <Select value={c.voice} onValueChange={(v) => onChange({ ...c, voice: v })}>
        <SelectTrigger data-testid={`character-voice-select-${c.name}`} className="bg-[#0A0908]"><SelectValue /></SelectTrigger>
        <SelectContent>
          {VOICES.map((v) => <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>)}
        </SelectContent>
      </Select>
      <button
        data-testid={`character-preview-btn-${c.name}`}
        onClick={preview}
        className="h-10 w-10 rounded-full border border-white/10 flex items-center justify-center text-stone-300 hover:text-amber-400 hover:border-amber-500/50 transition-colors"
        title="Ouvir"
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Volume2 className="w-4 h-4" />}
      </button>
    </div>
  );
};

export const CharactersPanel = ({ script, onSaved }) => {
  const update = async (c) => {
    const characters = script.characters.map((x) => (x.name === c.name ? c : x));
    try {
      onSaved(await api.updateScript(script.id, { characters }));
      toast.success(`Voz de ${c.name} actualizada`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const sampleFor = (name) => script.lines.find((l) => l.character === name)?.text || `Olá, eu sou ${name}.`;
  return (
    <div className="space-y-4">
      <p className="text-sm text-stone-400">
        Cada personagem tem uma voz própria, sempre em português de Portugal. Podes descrever o carácter da voz para orientar a interpretação.
      </p>
      {script.characters.map((c) => <CharacterRow key={c.name} c={c} sample={sampleFor(c.name)} onChange={update} />)}
    </div>
  );
};
