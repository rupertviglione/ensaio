import { useEffect, useState } from "react";
import { Volume2, Loader2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg, VOICES } from "@/lib/api";
import { playUrl } from "@/lib/audio";

const PreviewBtn = ({ c, sample }) => {
  const [busy, setBusy] = useState(false);
  const preview = async () => {
    setBusy(true);
    try {
      const url = await api.tts({ text: sample, voice: c.voice, character: c.name, style: c.style, el_voice_id: c.el_voice_id });
      setBusy(false);
      await playUrl(url);
    } catch (e) {
      toast.error(errMsg(e));
      setBusy(false);
    }
  };
  return (
    <button data-testid={`character-preview-btn-${c.name}`} onClick={preview} title="Ouvir"
      className="h-10 w-10 shrink-0 rounded-full border border-white/10 flex items-center justify-center text-stone-300 hover:text-amber-400 hover:border-amber-500/50 transition-colors">
      {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Volume2 className="w-4 h-4" />}
    </button>
  );
};

const ElevenSelect = ({ c, voices, onPick }) => {
  const [custom, setCustom] = useState("");
  const known = voices.some((v) => v.id === c.el_voice_id);
  return (
    <div className="space-y-2">
      <Select value={known ? c.el_voice_id : undefined} onValueChange={(id) => onPick(voices.find((v) => v.id === id))}>
        <SelectTrigger data-testid={`character-el-voice-select-${c.name}`} className="bg-[#0A0908]">
          <SelectValue placeholder={c.el_voice_name || c.el_voice_id || "Escolher voz ElevenLabs"} />
        </SelectTrigger>
        <SelectContent>
          {voices.map((v) => (
            <SelectItem key={v.id} value={v.id}>{v.name} {v.gender ? `· ${v.gender === "female" ? "fem." : v.gender === "male" ? "masc." : v.gender}` : ""} {v.accent ? `· ${v.accent}` : ""}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="flex gap-2">
        <Input data-testid={`character-el-voice-id-input-${c.name}`} value={custom} onChange={(e) => setCustom(e.target.value)}
          placeholder="Voice ID" className="bg-[#0A0908] h-9 text-xs font-mono" />
        <Button data-testid={`character-el-voice-id-save-${c.name}`} size="sm" variant="outline" disabled={!custom.trim()}
          onClick={() => { onPick({ id: custom.trim(), name: custom.trim(), owned: true }); setCustom(""); }}>Usar</Button>
      </div>
    </div>
  );
};

const CharacterRow = ({ c, sample, eleven, onChange, onEleven }) => (
  <div className="rounded-xl border border-white/[0.07] bg-[#141210] p-5 grid md:grid-cols-[1fr_260px_auto] gap-4 items-start" data-testid={`character-row-${c.name}`}>
    <div>
      <p className="font-mono text-sm tracking-widest font-bold text-sky-300">{c.name}</p>
      <Input data-testid={`character-style-input-${c.name}`} defaultValue={c.style}
        onBlur={(e) => e.target.value !== c.style && onChange({ ...c, style: e.target.value })}
        placeholder="Carácter da voz (ex.: velho, irónico, fala devagar)" className="mt-3 bg-[#0A0908]" />
    </div>
    {eleven ? (
      <ElevenSelect c={c} voices={eleven} onPick={(v) => onEleven(c, v)} />
    ) : (
      <Select value={c.voice} onValueChange={(v) => onChange({ ...c, voice: v })}>
        <SelectTrigger data-testid={`character-voice-select-${c.name}`} className="bg-[#0A0908]"><SelectValue /></SelectTrigger>
        <SelectContent>{VOICES.map((v) => <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>)}</SelectContent>
      </Select>
    )}
    <PreviewBtn c={c} sample={sample} />
  </div>
);

export const CharactersPanel = ({ script, onSaved }) => {
  const [info, setInfo] = useState(null);
  const [auto, setAuto] = useState(false);
  useEffect(() => { api.voices().then(setInfo).catch(() => setInfo({ provider: "openai" })); }, []);
  const eleven = info?.provider === "elevenlabs" ? info.elevenlabs : null;

  const update = async (c) => {
    const characters = script.characters.map((x) => (x.name === c.name ? c : x));
    try {
      onSaved(await api.updateScript(script.id, { characters }));
      toast.success(`${c.name} actualizado`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const setEleven = async (c, v) => {
    try {
      onSaved(await api.setElevenVoice(script.id, c.name, v));
      toast.success(`Voz de ${c.name}: ${v.name}`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const autoAssign = async () => {
    setAuto(true);
    try { onSaved(await api.autoVoices(script.id)); toast.success("Vozes atribuídas"); } catch (e) { toast.error(errMsg(e)); }
    setAuto(false);
  };
  if (!info) return <div className="flex justify-center py-12" data-testid="voices-loading"><Loader2 className="w-6 h-6 animate-spin text-amber-500" /></div>;
  const sampleFor = (name) => script.lines.find((l) => l.character === name)?.text || `Olá, eu sou ${name}.`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-stone-400 max-w-xl" data-testid="voice-provider-info">
          {eleven ? "Vozes ElevenLabs (modelo rápido Flash v2.5, em português). A OpenAI fica como alternativa automática." : "Vozes OpenAI em português de Portugal."}
        </p>
        {eleven && (
          <Button data-testid="auto-voices-btn" variant="outline" size="sm" onClick={autoAssign} disabled={auto} className="rounded-full">
            {auto ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Wand2 className="w-4 h-4 mr-2" />} Atribuir automaticamente
          </Button>
        )}
      </div>
      {script.characters.map((c) => (
        <CharacterRow key={c.name} c={c} sample={sampleFor(c.name)} eleven={eleven} onChange={update} onEleven={setEleven} />
      ))}
    </div>
  );
};
