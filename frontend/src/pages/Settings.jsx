import { useEffect, useState } from "react";
import { KeyRound, Loader2, CheckCircle2, XCircle, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/lib/api";

const HELP = {
  elevenlabs: "Vozes pt-PT (principal quando válida). Chave secreta sk_… em elevenlabs.io → Settings → API Keys, com Text to Speech e Voices: Read.",
  deepgram: "Escuta principal (nova-3 pt-PT). console.deepgram.com → API Keys.",
  gemini: "Escuta de reserva (Gemini Live). aistudio.google.com/apikey.",
};
const PERMS = { tts: "Text to Speech", stt: "Speech to Text", voices_read: "Voices: Read", voices_write: "Voices: Write", realtime_token: "Tokens Scribe" };

const Status = ({ k }) => {
  const st = k.status;
  if (!k.configured) return <p className="text-xs text-stone-500" data-testid={`key-status-${k.provider}`}>Sem chave.</p>;
  return (
    <div className="space-y-1 text-xs" data-testid={`key-status-${k.provider}`}>
      <p className="text-stone-400">
        Chave …<span className="font-mono text-stone-200" data-testid={`key-last4-${k.provider}`}>{k.last4}</span> · {k.source === "app" ? "guardada na app" : "do ficheiro backend/.env"}
      </p>
      {st && (
        <p className={`flex items-center gap-1 ${st.valid ? "text-emerald-400" : "text-rose-400"}`} data-testid={`key-valid-${k.provider}`}>
          {st.valid ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />} {st.message}
        </p>
      )}
      {st?.character_limit != null && (
        <p className="text-stone-400" data-testid={`key-credits-${k.provider}`}>Créditos: {st.character_count?.toLocaleString("pt-PT")} / {st.character_limit?.toLocaleString("pt-PT")} caracteres</p>
      )}
      {st?.balance && <p className="text-stone-400" data-testid={`key-credits-${k.provider}`}>Saldo: {st.balance}</p>}
      {(st?.balance_error || st?.credits_error) && <p className="text-stone-500" data-testid={`key-credits-note-${k.provider}`}>{st.balance_error || st.credits_error}</p>}
      {st?.permissions && (
        <div className="flex flex-wrap gap-1.5 pt-1" data-testid={`key-perms-${k.provider}`}>
          {Object.entries(PERMS).map(([p, label]) => (
            <span key={p} className={`px-2 py-0.5 rounded-full border ${st.permissions[p] ? "border-emerald-500/40 text-emerald-300" : st.permissions[p] === false ? "border-rose-500/40 text-rose-300" : "border-white/10 text-stone-500"}`}>{label}</span>
          ))}
        </div>
      )}
    </div>
  );
};

const KeyCard = ({ k, onUpdate }) => {
  const [val, setVal] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (fn, ok) => {
    setBusy(true);
    try { const r = await fn(); onUpdate(r); ok?.(r); } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  const save = () => run(() => api.setKey(k.provider, val.trim()), (r) => {
    if (r.attempt && !r.attempt.valid) toast.error(r.attempt.message || "Chave inválida");
    else { toast.success(`Chave ${k.label} guardada`); setVal(""); }
  });
  const test = async () => {
    setBusy(true);
    try {
      const { attempt } = await api.validateKey(k.provider, val.trim());
      attempt.valid ? toast.success(`${attempt.message} (não guardada)`) : toast.error(attempt.message || "Chave inválida");
    } catch (e) { toast.error(errMsg(e)); }
    setBusy(false);
  };
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-[#141210] p-6 space-y-4" data-testid={`key-card-${k.provider}`}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-serif text-2xl text-stone-100 flex items-center gap-2"><KeyRound className="w-5 h-5 text-amber-500" /> Chave {k.label}</h2>
        {k.configured && (
          <button data-testid={`key-check-btn-${k.provider}`} onClick={() => run(() => api.checkKey(k.provider))} disabled={busy} className="text-stone-400 hover:text-amber-400 text-xs flex items-center gap-1">
            <RefreshCw className="w-3.5 h-3.5" /> Verificar
          </button>
        )}
      </div>
      <p className="text-sm text-stone-500">{HELP[k.provider]}</p>
      <Status k={k} />
      <div className="flex gap-2">
        <Input data-testid={`key-input-${k.provider}`} type="password" autoComplete="off" value={val} onChange={(e) => setVal(e.target.value)} placeholder="Colar a chave aqui" className="bg-[#0A0908] font-mono" />
        <Button data-testid={`key-test-btn-${k.provider}`} variant="outline" onClick={test} disabled={busy || !val.trim()} className="rounded-full" title="Validar sem guardar">
          Testar
        </Button>
        <Button data-testid={`key-save-btn-${k.provider}`} onClick={save} disabled={busy || !val.trim()} className="rounded-full">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Validar e guardar"}
        </Button>
        {k.source === "app" && (
          <Button data-testid={`key-remove-btn-${k.provider}`} variant="outline" onClick={() => run(() => api.setKey(k.provider, ""), () => toast("Chave removida; a usar o backend/.env"))} disabled={busy} className="rounded-full" title="Remover">
            <Trash2 className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  );
};

export default function Settings() {
  const [data, setData] = useState(null);
  useEffect(() => { api.settingsKeys().then(setData).catch((e) => toast.error(errMsg(e))); }, []);
  const update = (r) => setData((d) => ({ ...d, tts_primary: r.tts_primary ?? d.tts_primary, keys: d.keys.map((k) => (k.provider === r.provider ? r : k)) }));
  return (
    <div className="max-w-3xl mx-auto px-6 md:px-10 py-12 space-y-8" data-testid="settings-page">
      <div>
        <h1 className="font-serif text-4xl sm:text-5xl text-stone-100">Definições</h1>
        <p className="text-sm text-stone-400 mt-3">As chaves ficam guardadas no servidor e têm prioridade sobre o ficheiro backend/.env. Nunca são enviadas para o browser.</p>
        {data && <p className="text-xs font-mono tracking-widest text-stone-500 mt-2" data-testid="tts-primary">VOZ PRINCIPAL: {data.tts_primary === "elevenlabs" ? "ELEVENLABS" : "EDGE PT-PT"}</p>}
      </div>
      {!data ? <Loader2 className="w-6 h-6 animate-spin text-amber-500" /> : data.keys.map((k) => <KeyCard key={k.provider} k={k} onUpdate={update} />)}
    </div>
  );
}
