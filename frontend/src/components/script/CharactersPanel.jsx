import { useEffect, useState } from "react";
import { Volume2, Loader2, Wand2, Pencil, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg, VOICES, voiceBody } from "@/lib/api";
import { playUrl } from "@/lib/audio";

const ENGINES = [
  { id: "auto", label: "Automático (principal da app)" },
  { id: "edge", label: "Edge pt-PT (grátis)" },
  { id: "openai", label: "OpenAI (reserva)" },
  { id: "elevenlabs", label: "ElevenLabs (opcional, gasta créditos)" },
];
const comboKey = (c) => `${c.edge_voice}|${c.edge_pitch}|${c.edge_rate}`;

const PreviewBtn = ({ c, sample, scriptId }) => {
  const [busy, setBusy] = useState(false);
  const preview = async () => {
    setBusy(true);
    try {
      const url = await api.tts({ text: sample, ...voiceBody(c, scriptId) });
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

const Tune = ({ label, unit, value, onCommit, testid }) => {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-[11px] font-mono text-stone-500">
        <span>{label}</span><span data-testid={`${testid}-value`} className="text-stone-300">{v > 0 ? `+${v}` : v}{unit}</span>
      </div>
      <Slider data-testid={testid} min={-30} max={30} step={2} value={[v]} onValueChange={([x]) => setV(x)} onValueCommit={([x]) => onCommit(x)} />
    </div>
  );
};

const ElevenSelect = ({ c, voices, onPick }) => {
  const [custom, setCustom] = useState("");
  const known = voices.some((v) => v.id === c.el_voice_id);
  return (
    <div className="space-y-2 rounded-lg border border-white/[0.06] p-2">
      {c.el_voice_id
        ? <p className="text-xs text-emerald-300 truncate" data-testid={`character-el-active-${c.name}`}>ElevenLabs: {c.el_voice_name || c.el_voice_id}</p>
        : <p className="text-[11px] text-stone-500">Escolhe uma voz ElevenLabs PT-PT (gasta créditos).</p>}
      {voices.length > 0 && (
        <Select value={known ? c.el_voice_id : undefined} onValueChange={(id) => onPick(voices.find((v) => v.id === id))}>
          <SelectTrigger data-testid={`character-el-voice-select-${c.name}`} className="bg-[#0A0908]"><SelectValue placeholder="Voz ElevenLabs PT-PT" /></SelectTrigger>
          <SelectContent>{voices.map((v) => <SelectItem key={v.id} value={v.id}>{v.name} {v.gender ? `· ${v.gender === "female" ? "fem." : "masc."}` : ""}</SelectItem>)}</SelectContent>
        </Select>
      )}
      <div className="flex gap-2">
        <Input data-testid={`character-el-voice-id-input-${c.name}`} value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Voice ID" className="bg-[#0A0908] h-9 text-xs font-mono" />
        <Button data-testid={`character-el-voice-id-save-${c.name}`} size="sm" variant="outline" disabled={!custom.trim()}
          onClick={() => { onPick({ id: custom.trim(), name: custom.trim() }); setCustom(""); }}>Usar</Button>
      </div>
    </div>
  );
};

const VoiceControls = ({ c, info, onChange, onEleven }) => (
  <div className="space-y-3">
    <Select value={c.tts || "auto"} onValueChange={(v) => (v === "elevenlabs" && !c.el_voice_id ? onChange({ ...c, tts: v }, true) : onChange({ ...c, tts: v }))}>
      <SelectTrigger data-testid={`character-engine-select-${c.name}`} className="bg-[#0A0908] h-9 text-xs"><SelectValue /></SelectTrigger>
      <SelectContent>{ENGINES.filter((e) => e.id !== "elevenlabs" || info.eleven_configured).map((e) => <SelectItem key={e.id} value={e.id}>{e.label}</SelectItem>)}</SelectContent>
    </Select>
    {(c.tts || "auto") === "auto" && info.provider === "elevenlabs" && c.el_voice_id && (
      <p className="text-xs text-emerald-300" data-testid={`character-auto-eleven-${c.name}`}>ElevenLabs: {c.el_voice_name || c.el_voice_id} (Edge como reserva)</p>
    )}
    {["edge", "auto"].includes(c.tts || "auto") && (
      <>
        <Select value={c.edge_voice} onValueChange={(v) => onChange({ ...c, edge_voice: v })}>
          <SelectTrigger data-testid={`character-voice-select-${c.name}`} className="bg-[#0A0908]"><SelectValue placeholder="Voz pt-PT" /></SelectTrigger>
          <SelectContent>{info.edge.map((v) => <SelectItem key={v.id} value={v.id}>{v.name} · {v.gender === "female" ? "feminina" : "masculina"} · pt-PT</SelectItem>)}</SelectContent>
        </Select>
        <Tune testid={`character-pitch-${c.name}`} label="TOM" unit="Hz" value={c.edge_pitch} onCommit={(x) => onChange({ ...c, edge_pitch: x })} />
        <Tune testid={`character-rate-${c.name}`} label="RITMO" unit="%" value={c.edge_rate} onCommit={(x) => onChange({ ...c, edge_rate: x })} />
      </>
    )}
    {c.tts === "openai" && (
      <Select value={c.voice} onValueChange={(v) => onChange({ ...c, voice: v })}>
        <SelectTrigger data-testid={`character-openai-voice-select-${c.name}`} className="bg-[#0A0908]"><SelectValue /></SelectTrigger>
        <SelectContent>{VOICES.map((v) => <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>)}</SelectContent>
      </Select>
    )}
    {c.tts === "elevenlabs" && <ElevenSelect c={c} voices={info.elevenlabs || []} onPick={(v) => onEleven(c, v)} />}
  </div>
);

const CharacterRow = ({ c, sample, info, dup, onChange, onEleven, onRename, scriptId }) => (
  <div className="rounded-xl border border-white/[0.07] bg-[#141210] p-5 grid md:grid-cols-[1fr_280px_auto] gap-4 items-start" data-testid={`character-row-${c.name}`}>
    <div>
      <div className="flex items-center gap-2">
        <p className="font-mono text-sm tracking-widest font-bold text-sky-300">{c.name}</p>
        <button data-testid={`character-rename-btn-${c.name}`} title="Mudar o nome (se já existir, junta as personagens)"
          onClick={() => { const n = window.prompt("Novo nome da personagem", c.name); if (n?.trim() && n.trim().toUpperCase() !== c.name) onRename(c.name, n.trim()); }}
          className="text-stone-500 hover:text-amber-400 transition-colors"><Pencil className="w-3.5 h-3.5" /></button>
      </div>
      <Input data-testid={`character-style-input-${c.name}`} defaultValue={c.style}
        onBlur={(e) => e.target.value !== c.style && onChange({ ...c, style: e.target.value })}
        placeholder="Carácter da voz (usado pela voz OpenAI de reserva)" className="mt-3 bg-[#0A0908]" />
      {dup && <p data-testid={`character-dup-warning-${c.name}`} className="mt-2 text-xs text-amber-300 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Mesma voz, tom e ritmo que {dup}.</p>}
    </div>
    <VoiceControls c={c} info={info} onChange={onChange} onEleven={onEleven} />
    <PreviewBtn c={c} sample={sample} scriptId={scriptId} />
  </div>
);

export const CharactersPanel = ({ script, onSaved }) => {
  const [info, setInfo] = useState(null);
  const [auto, setAuto] = useState(false);
  useEffect(() => { api.voices().then(setInfo).catch(() => setInfo({ edge: [], elevenlabs: [] })); }, []);

  const update = async (c, silent) => {
    const characters = script.characters.map((x) => (x.name === c.name ? c : x));
    try {
      onSaved(await api.updateScript(script.id, { characters }));
      if (!silent) toast.success(`${c.name} actualizado`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const setEleven = async (c, v) => {
    try {
      onSaved(await api.setElevenVoice(script.id, c.name, v));
      toast.success(`Voz ElevenLabs de ${c.name}: ${v.name}`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const autoAssign = async () => {
    setAuto(true);
    try { onSaved(await api.autoVoices(script.id)); toast.success("Vozes pt-PT atribuídas"); } catch (e) { toast.error(errMsg(e)); }
    setAuto(false);
  };
  if (!info) return <div className="flex justify-center py-12" data-testid="voices-loading"><Loader2 className="w-6 h-6 animate-spin text-amber-500" /></div>;
  const sampleFor = (name) => script.lines.find((l) => l.character === name)?.text || `Olá, eu sou ${name}.`;
  const edgeLike = (x) => ["edge", "auto"].includes(x.tts || "auto");
  const dupOf = (c) => edgeLike(c) && script.characters.find((x) => x.name !== c.name && edgeLike(x) && comboKey(x) === comboKey(c))?.name;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="max-w-xl space-y-1">
          <p className="text-sm text-stone-400" data-testid="voice-provider-info">
            Vozes neurais Microsoft Edge em português de Portugal (grátis). Cada personagem tem uma combinação própria de voz, tom e ritmo. Se o Edge falhar, usa-se a OpenAI.
          </p>
          {info.prompter && <p className="text-xs text-stone-500" data-testid="prompter-voice-info">Apontador: {info.prompter.edge_voice?.split("-")[2]?.replace("Neural", "")} · {info.prompter.edge_pitch > 0 ? "+" : ""}{info.prompter.edge_pitch}Hz · {info.prompter.edge_rate > 0 ? "+" : ""}{info.prompter.edge_rate}%</p>}
        </div>
        <Button data-testid="auto-voices-btn" variant="outline" size="sm" onClick={autoAssign} disabled={auto} className="rounded-full">
          {auto ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Wand2 className="w-4 h-4 mr-2" />} Atribuir automaticamente
        </Button>
      </div>
      {script.characters.map((c) => (
        <CharacterRow key={c.name} scriptId={script.id} c={c} sample={sampleFor(c.name)} info={info} dup={dupOf(c)} onChange={update} onEleven={setEleven}
          onRename={async (old, n) => { try { onSaved(await api.renameCharacter(script.id, old, n)); toast.success("Personagem actualizada"); } catch (e) { toast.error(errMsg(e)); } }} />
      ))}
    </div>
  );
};
