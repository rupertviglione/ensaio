import { api, errMsg, WS_BASE } from "./api";

const WORKLET = `
class Pcm16k extends AudioWorkletProcessor {
  constructor() { super(); this.ratio = sampleRate / 16000; this.pos = 0; this.acc = 0; this.cnt = 0; this.out = new Int16Array(800); this.n = 0; this.sq = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.acc += ch[i]; this.cnt++; this.pos++;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const s = Math.max(-1, Math.min(1, this.acc / this.cnt));
        this.acc = 0; this.cnt = 0; this.sq += s * s;
        this.out[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        if (this.n === 800) { this.port.postMessage({ pcm: this.out.buffer.slice(0), level: Math.sqrt(this.sq / 800) }); this.n = 0; this.sq = 0; }
      }
    }
    return true;
  }
}
registerProcessor("pcm16k", Pcm16k);`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MAX_QUEUE = 600; // 30 s of 50 ms chunks

function b64(buf) {
  const u = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return btoa(s);
}

const readMsg = async (data) => JSON.parse(typeof data === "string" ? data : await data.text());

class MicStream {
  async open(onChunk, onLevel, onLost) {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
    this.stream.getAudioTracks().forEach((t) => { t.onended = () => onLost?.("O microfone foi desligado."); });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.resume();
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await this.ctx.audioWorklet.addModule(url);
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "pcm16k");
    this.node.port.onmessage = (e) => { onLevel?.(e.data.level); onChunk(e.data.pcm); };
    const mute = this.ctx.createGain();
    mute.gain.value = 0;
    src.connect(this.node);
    this.node.connect(mute);
    mute.connect(this.ctx.destination);
  }

  alive() { return !!this.stream?.getAudioTracks().some((t) => t.readyState === "live"); }

  resume() { if (this.ctx?.state === "suspended") this.ctx.resume().catch(() => {}); }

  close() {
    this.stream?.getTracks().forEach((t) => { t.onended = null; t.stop(); });
    this.ctx?.close().catch(() => {});
  }
}

// Streaming engine over WebSocket. One socket per block: clear() starts a fresh socket (new hints, empty transcript)
// while the old one is finalised and ignored. Audio is queued while (re)connecting, so no words are lost.
// Words still arriving for a closed block (e.g. the final for the last word): resolves on the next update or after ms.
const waitTail = (tg, ms, ok = () => true) => new Promise((res) => {
  const text = () => [...tg.finals, tg.partial].filter(Boolean).join(" ");
  const done = () => { clearTimeout(timer); tg.onUpdate = null; res(text()); };
  const timer = setTimeout(done, ms);
  tg.onUpdate = () => { if (ok(text())) done(); };
});

class WsEngine {
  constructor(onText, onFatal) {
    this.cur = { finals: [], partial: "" };
    Object.assign(this, { onText, onFatal, queue: [], active: true, closed: false, fails: 0, hints: [] });
  }

  get finals() { return this.cur.finals; }
  set finals(v) { this.cur.finals = v; }
  get partial() { return this.cur.partial; }
  set partial(v) { this.cur.partial = v; }

  // Each socket writes into the transcript of the block it was opened for.
  feed(ws, fn) {
    return async (e) => {
      const tg = ws.target || this.cur;
      if ((await fn(e, tg)) === false) return;
      tg.onUpdate?.();
      if (tg === this.cur) this.onText();
    };
  }

  text() { return [...this.finals, this.partial].filter(Boolean).join(" "); }

  async connect(hints = this.hints) {
    this.hints = hints;
    const ws = await this.open(hints);
    if (this.closed) { this.retire(ws); return; }
    ws.target = this.cur;
    this.ws = ws;
    ws.onclose = (e) => {
      if (this.ws !== ws) return;
      this.ws = null;
      console.warn(`[${this.name}] ligação fechada`, e.code, e.reason);
      if (!this.closed) this.reconnect(true);
    };
    this.fails = 0;
    while (this.queue.length && ws.readyState === 1) this.write(ws, this.queue.shift());
  }

  async reconnect(dropped = false) {
    if (this.partial) { this.finals.push(this.partial); this.partial = ""; }
    else if (dropped && this.ring?.length && !this.queue.length) this.queue.push(...this.ring.slice(-30)); // replay ~1.5 s lost in the drop
    if (this.reconnecting) return;
    this.reconnecting = true;
    while (!this.closed) {
      try { await this.connect(); console.info(`[${this.name}] religado`); break; } catch (e) {
        if (++this.fails >= 3) { this.closed = true; this.onFatal(e); break; }
        await sleep(300 * this.fails);
      }
    }
    this.reconnecting = false;
  }

  own(ws, fn) { return (e) => { if (this.ws === ws) fn(e); }; }

  send(pcm) {
    if (this.closed) return;
    this.lastSend = performance.now();
    this.ring = this.ring || [];
    this.ring.push(pcm);
    if (this.ring.length > 40) this.ring.shift();
    if (this.ws?.readyState === 1) this.write(this.ws, pcm);
    else { this.queue.push(pcm); if (this.queue.length > MAX_QUEUE) this.queue.shift(); }
  }

  clear(hints) {
    const old = this.ws;
    const oldT = this.cur;
    this.ws = null;
    this.cur = { finals: [], partial: "" };
    this.onText();
    if (old) this.retire(old);
    this.ring = [];
    this.hints = hints || this.hints;
    if (!this.closed && !this.reconnecting) this.reconnect();
    return (ms, ok) => waitTail(oldT, ms, ok);
  }

  setActive(on) { this.active = on; }
  dead() { return !this.closed && !this.reconnecting && (!this.ws || this.ws.readyState > 1); }
  pending() { return this.queue.splice(0); }
  close() { this.closed = true; const ws = this.ws; this.ws = null; if (ws) this.retire(ws); }
}

const waitOpen = (ws, name) => new Promise((res, rej) => {
  ws.onopen = () => res(ws);
  ws.onerror = () => rej(new Error(`Ligação ${name} falhou`));
  ws.onclose = (e) => rej(new Error(`Ligação ${name} fechada (${e.code}${e.reason ? `: ${e.reason}` : ""})`));
});

// Deepgram nova-3 streaming (pt-PT). Default: through our backend proxy (same origin, key stays on the server);
// fallback: direct browser connection with a short-lived token. Keyterms = rare words / names of the current + next block.
class DeepgramEngine extends WsEngine {
  name = "deepgram";

  async open(hints) {
    if (!this.direct) {
      try { return await this.openProxy(hints); } catch (e) {
        if (e.fatal) throw e;
        console.warn("[deepgram] proxy falhou, a tentar ligação directa:", e.message);
        this.direct = true;
      }
    }
    return this.openDirect(hints);
  }

  async openProxy(hints) {
    const q = new URLSearchParams();
    hints.slice(0, 100).forEach((k) => q.append("keyterm", k));
    const ws = new WebSocket(`${WS_BASE}/api/stt/deepgram?${q}`);
    ws.binaryType = "arraybuffer";
    await waitOpen(ws, "Deepgram (proxy)");
    await new Promise((res, rej) => {
      const t = setTimeout(() => rej(new Error("Deepgram (proxy) não respondeu")), 9000);
      ws.onclose = (e) => { clearTimeout(t); rej(new Error(`Deepgram (proxy) fechou (${e.code})`)); };
      ws.onmessage = async (e) => {
        const m = await readMsg(e.data);
        if (m.type === "Ready") { clearTimeout(t); res(); }
        if (m.type === "Error") { clearTimeout(t); const err = new Error(m.message); err.fatal = true; rej(err); }
      };
    });
    this.via = "proxy";
    return this.attach(ws);
  }

  async openDirect(hints) {
    const cfg = await api.sttDeepgram();
    const q = new URLSearchParams(cfg.params);
    hints.slice(0, 100).forEach((k) => q.append("keyterm", k));
    const ws = new WebSocket(`${cfg.url}?${q}`, ["bearer", cfg.token]);
    ws.binaryType = "arraybuffer";
    await waitOpen(ws, "Deepgram");
    this.via = "direct";
    return this.attach(ws);
  }

  attach(ws) {
    ws.onerror = () => {};
    ws.onmessage = this.feed(ws, async (e, tg) => {
      const m = await readMsg(e.data);
      if (m.type !== "Results") return false;
      const t = (m.channel?.alternatives?.[0]?.transcript || "").trim();
      if (m.is_final) { if (t) tg.finals.push(t); tg.partial = ""; } else tg.partial = t;
      return true;
    });
    ws.keep = setInterval(() => {
      if (ws.readyState === 1 && performance.now() - (this.lastSend || 0) > 4000) ws.send(JSON.stringify({ type: "KeepAlive" }));
    }, 4000);
    return ws;
  }

  write(ws, pcm) { ws.send(pcm); }

  // Local VAD heard the actor stop: ask Deepgram to emit the final for what it has right now.
  flush() { if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ type: "Finalize" })); }

  retire(ws) {
    clearInterval(ws.keep);
    try { if (ws.readyState === 1) { ws.send(JSON.stringify({ type: "Finalize" })); ws.send(JSON.stringify({ type: "CloseStream" })); } } catch { /* fechado */ }
    setTimeout(() => { try { ws.close(); } catch { /* fechado */ } }, 1500);
  }
}

// Gemini Live transcription (reserve) with an ephemeral token; custom vocabulary = expected words/phrases of the block.
class GeminiEngine extends WsEngine {
  name = "gemini";

  async open(hints) {
    const cfg = await api.sttGemini();
    const ws = new WebSocket(`${cfg.url}?access_token=${encodeURIComponent(cfg.token)}`);
    await waitOpen(ws, "Gemini");
    ws.send(JSON.stringify({ setup: { model: `models/${cfg.model}`, generationConfig: { responseModalities: ["TEXT"] },
      realtimeInputConfig: { automaticActivityDetection: { endOfSpeechSensitivity: "END_SENSITIVITY_HIGH", silenceDurationMs: 200, prefixPaddingMs: 40 } },
      inputAudioTranscription: { languageCodes: [cfg.language], customVocabulary: [...(this.context || []), ...hints].slice(0, 200) } } }));
    await new Promise((res, rej) => {
      const t = setTimeout(() => rej(new Error("Gemini não respondeu")), 6000);
      ws.onclose = (e) => { clearTimeout(t); rej(new Error(`Gemini recusou a ligação (${e.code}${e.reason ? `: ${e.reason}` : ""})`)); };
      ws.onmessage = async (e) => { const m = await readMsg(e.data); if (m.setupComplete) { clearTimeout(t); res(); } };
    });
    ws.onerror = () => {};
    ws.onmessage = this.feed(ws, async (e, tg) => {
      const sc = (await readMsg(e.data)).serverContent;
      if (!sc) return false;
      if (sc.inputTranscription) { const t = (sc.inputTranscription.text || "").trim(); if (t) tg.finals.push(t); tg.partial = ""; }
      else if (sc.interimInputTranscription) tg.partial = (sc.interimInputTranscription.text || "").trim();
      else return false;
      return true;
    });
    return ws;
  }

  write(ws, pcm) { ws.send(JSON.stringify({ realtimeInput: { audio: { data: b64(pcm), mimeType: "audio/pcm;rate=16000" } } })); }

  retire(ws) {
    try { if (ws.readyState === 1) ws.send(JSON.stringify({ realtimeInput: { audioStreamEnd: true } })); } catch { /* fechado */ }
    setTimeout(() => { try { ws.close(); } catch { /* fechado */ } }, 1500);
  }
}

// Optional (opt-in, spends ElevenLabs credit): localStorage "ensaio-stt" = "scribe".
class ScribeEngine extends WsEngine {
  name = "scribe";

  async open() {
    const cfg = await api.sttToken();
    const q = new URLSearchParams({ model_id: cfg.model_id, token: cfg.token, audio_format: "pcm_16000", language_code: cfg.language_code, commit_strategy: "vad" });
    const ws = new WebSocket(`${cfg.url}?${q}`);
    await waitOpen(ws, "Scribe");
    ws.onerror = () => {};
    ws.onmessage = this.feed(ws, async (e, tg) => {
      const m = await readMsg(e.data);
      if (m.message_type === "partial_transcript") tg.partial = m.text || "";
      else if (m.message_type === "committed_transcript") { if (m.text?.trim()) tg.finals.push(m.text.trim()); tg.partial = ""; }
      else return false;
      return true;
    });
    return ws;
  }

  write(ws, pcm) { ws.send(JSON.stringify({ message_type: "input_audio_chunk", audio_base_64: b64(pcm), commit: false, sample_rate: 16000 })); }
  retire(ws) { setTimeout(() => { try { ws.close(); } catch { /* fechado */ } }, 300); }
}

// Last resort: browser Web Speech.
class WebSpeechEngine {
  name = "webspeech";

  constructor(onText) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    Object.assign(this, { onText, prefix: "", cur: "", closed: false, active: true, gen: 0 });
    this.start = () => {
      const gen = this.gen;
      const r = new SR();
      r.lang = "pt-PT";
      r.continuous = true;
      r.interimResults = true;
      r.onresult = (e) => {
        if (gen !== this.gen) return;
        let t = "";
        for (let i = 0; i < e.results.length; i++) t += `${e.results[i][0].transcript} `;
        this.cur = t.trim();
        this.onText();
      };
      r.onerror = () => {};
      r.onend = () => {
        if (gen !== this.gen) return;
        this.prefix = this.text();
        this.cur = "";
        if (!this.closed) try { r.start(); } catch { /* já activo */ }
      };
      this.r = r;
      r.start();
    };
    this.start();
  }

  text() { return `${this.prefix} ${this.cur}`.trim(); }
  send() {}
  pending() { return []; }
  setActive(on) { this.active = on; }
  clear() {
    const old = this.text();
    this.gen++;
    this.prefix = "";
    this.cur = "";
    this.onText();
    try { this.r.abort(); } catch { /* ignorar */ }
    if (!this.closed) this.start();
    return () => Promise.resolve(old);
  }
  close() { this.closed = true; this.gen++; try { this.r.abort(); } catch { /* ignorar */ } }
}

export const hasWebSpeech = () => !!(window.SpeechRecognition || window.webkitSpeechRecognition);

const ENGINES = { deepgram: DeepgramEngine, gemini: GeminiEngine, scribe: ScribeEngine };
const order = () => {
  const pref = localStorage.getItem("ensaio-stt");
  if (pref === "scribe") return ["scribe", "deepgram", "gemini", "webspeech"];
  if (pref === "gemini") return ["gemini", "deepgram", "webspeech"];
  return ["deepgram", "gemini", "webspeech"];
};

export class Listener {
  constructor({ onText, onLevel, onNotice, onEngine, onMic, onSilence }) {
    Object.assign(this, { onText, onLevel, onNotice, onEngine, onMic, onSilence, base: "", kind: "none", lastChunkAt: 0, hints: [], context: [], tried: new Set(), lastUpgrade: 0 });
    this.emit = () => this.onText([this.base, this.engine?.text() || ""].filter(Boolean).join(" "));
    this.wake = () => { if (!document.hidden) this.revive(); };
  }

  async openMic() {
    this.mic?.close();
    this.mic = new MicStream();
    const level = (v) => {
      // simple VAD for latency: noise floor tracks quiet chunks; "voice" = clearly above it
      const now = performance.now();
      this.floor = v < (this.floor ?? v) ? v : (this.floor ?? v) * 1.001;
      if (v > Math.max(0.012, this.floor * 4)) { this.lastVoiceAt = now; this.voiced = true; }
      else if (this.voiced && now - this.lastVoiceAt >= 120) { this.voiced = false; this.onSilence?.(); }
      this.onLevel?.(v);
    };
    await this.mic.open((pcm) => { this.lastChunkAt = performance.now(); this.engine?.send(pcm); }, level, (why) => this.micLost(why));
    this.lost = false;
    this.lastChunkAt = performance.now();
    this.onMic?.(null);
  }

  micLost(why) {
    if (this.lost || this.closed) return;
    this.lost = true;
    console.warn("[ensaio] microfone perdido:", why);
    this.onMic?.(why);
  }

  async open(hints = [], context = []) {
    this.hints = hints;
    this.context = context;
    await this.openMic();
    await this.start([]);
    document.addEventListener("visibilitychange", this.wake);
    window.addEventListener("focus", this.wake);
    this.watch = setInterval(() => this.revive(), 3000);
  }

  // Keeps mic + recognition alive: resume audio, reconnect a dropped socket, come back to the primary engine.
  revive() {
    if (this.closed) return;
    this.mic?.resume();
    const now = performance.now();
    if (!this.lost && (!this.mic?.alive() || (this.mic?.ctx?.state === "running" && now - this.lastChunkAt > 4000))) {
      this.micLost("O microfone deixou de enviar som.");
    }
    if (!this.engine) { this.tried.clear(); this.start([]); return; }
    if (this.engine.dead?.()) this.engine.reconnect();
    if (this.kind !== order()[0] && now - this.lastUpgrade > 30000) this.upgrade();
  }

  async upgrade() {
    this.lastUpgrade = performance.now();
    const k = order()[0];
    const e = new ENGINES[k](this.emit, (err) => this.fallback(e, err));
    try {
      e.context = this.context;
      await e.connect(this.hints);
    } catch { e.close(); return; }
    const old = this.engine;
    if (this.closed || !old) { e.close(); return; }
    this.base = [this.base, old.text()].filter(Boolean).join(" ");
    e.queue = old.pending?.() || [];
    old.close();
    this.engine = e;
    this.tried = new Set([k]);
    this.setKind(k);
    console.info(`[ensaio] voltei ao motor ${k}`);
  }

  async start(carry) {
    for (const k of order()) {
      if (this.tried.has(k)) continue;
      this.tried.add(k);
      if (k === "webspeech") {
        if (!hasWebSpeech()) continue;
        try { this.engine = new WebSpeechEngine(this.emit); this.setKind(k); return; } catch { continue; }
      }
      const e = new ENGINES[k](this.emit, (err) => this.fallback(e, err));
      e.queue = [...carry];
      e.context = this.context;
      this.engine = e;
      try {
        await e.connect(this.hints);
        this.setKind(k);
        return;
      } catch (err) {
        carry = e.pending();
        e.close();
        this.engine = null;
        this.notice(k, err);
      }
    }
    this.engine = null;
    this.setKind("none");
  }

  notice(k, err) {
    const msg = errMsg(err);
    console.warn(`[ensaio] motor ${k} indisponível:`, msg);
    this.onNotice?.(msg);
  }

  setKind(k) { this.kind = k; this.onEngine?.(k); }

  flush() { this.engine?.flush?.(); }

  fallback(e, err) {
    if (this.engine !== e) return;
    this.notice(e.name, err);
    this.base = [this.base, e.text()].filter(Boolean).join(" ");
    const carry = e.pending();
    e.close();
    this.engine = null;
    this.start(carry);
  }

  // New block: empty transcript, fresh recognition with the block's expected words as hints.
  clear(hints, context) {
    this.hints = hints || this.hints;
    this.context = context || this.context;
    if (this.engine) this.engine.context = this.context;
    const base = this.base;
    this.base = "";
    const tail = this.engine?.clear(this.hints);
    this.emit();
    return async (ms, ok) => [base, tail ? await tail(ms, ok && ((t) => ok([base, t].join(" ")))) : ""].filter(Boolean).join(" ");
  }

  setActive(on) { this.engine?.setActive(on); }
  close() {
    this.closed = true;
    clearInterval(this.watch);
    document.removeEventListener("visibilitychange", this.wake);
    window.removeEventListener("focus", this.wake);
    this.engine?.close();
    this.mic?.close();
  }
}
