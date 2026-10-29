import { api, errMsg } from "./api";

const WORKLET = `
class Pcm16k extends AudioWorkletProcessor {
  constructor() { super(); this.ratio = sampleRate / 16000; this.pos = 0; this.acc = 0; this.cnt = 0; this.out = new Int16Array(1600); this.n = 0; this.sq = 0; }
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
        if (this.n === 1600) { this.port.postMessage({ pcm: this.out.buffer.slice(0), level: Math.sqrt(this.sq / 1600) }); this.n = 0; this.sq = 0; }
      }
    }
    return true;
  }
}
registerProcessor("pcm16k", Pcm16k);`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MAX_QUEUE = 300; // 30 s of 100 ms chunks

function b64(buf) {
  const u = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return btoa(s);
}

const readMsg = async (data) => JSON.parse(typeof data === "string" ? data : await data.text());

class MicStream {
  async open(onChunk, onLevel) {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
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

  close() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close().catch(() => {});
  }
}

// Streaming engine over WebSocket. One socket per block: clear() starts a fresh socket (new hints, empty transcript)
// while the old one is finalised and ignored. Audio is queued while (re)connecting, so no words are lost.
class WsEngine {
  constructor(onText, onFatal) {
    Object.assign(this, { onText, onFatal, finals: [], partial: "", queue: [], active: true, closed: false, fails: 0, hints: [] });
  }

  text() { return [...this.finals, this.partial].filter(Boolean).join(" "); }

  async connect(hints = this.hints) {
    this.hints = hints;
    const ws = await this.open(hints);
    if (this.closed) { this.retire(ws); return; }
    this.ws = ws;
    ws.onclose = (e) => {
      if (this.ws !== ws) return;
      this.ws = null;
      console.warn(`[${this.name}] ligação fechada`, e.code, e.reason);
      if (!this.closed) this.reconnect();
    };
    this.fails = 0;
    while (this.queue.length && ws.readyState === 1) this.write(ws, this.queue.shift());
  }

  async reconnect() {
    if (this.partial) { this.finals.push(this.partial); this.partial = ""; }
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
    if (!this.active || this.closed) return;
    if (this.ws?.readyState === 1) this.write(this.ws, pcm);
    else { this.queue.push(pcm); if (this.queue.length > MAX_QUEUE) this.queue.shift(); }
  }

  clear(hints) {
    const old = this.ws;
    this.ws = null;
    this.finals = [];
    this.partial = "";
    this.onText();
    if (old) this.retire(old);
    this.hints = hints || this.hints;
    if (!this.closed && !this.reconnecting) this.reconnect();
  }

  setActive(on) { this.active = on; }
  pending() { return this.queue.splice(0); }
  close() { this.closed = true; const ws = this.ws; this.ws = null; if (ws) this.retire(ws); }
}

const waitOpen = (ws, name) => new Promise((res, rej) => {
  ws.onopen = () => res(ws);
  ws.onerror = () => rej(new Error(`Ligação ${name} falhou`));
  ws.onclose = (e) => rej(new Error(`Ligação ${name} fechada (${e.code}${e.reason ? `: ${e.reason}` : ""})`));
});

// Deepgram nova-3 streaming (pt-PT) with a short-lived token from the backend; keyterms = expected words of the block.
class DeepgramEngine extends WsEngine {
  name = "deepgram";

  async open(hints) {
    const cfg = await api.sttDeepgram();
    const q = new URLSearchParams(cfg.params);
    hints.slice(0, 40).forEach((k) => q.append("keyterm", k));
    const ws = new WebSocket(`${cfg.url}?${q}`, ["bearer", cfg.token]);
    ws.binaryType = "arraybuffer";
    await waitOpen(ws, "Deepgram");
    ws.onerror = () => {};
    ws.onmessage = this.own(ws, async (e) => {
      const m = await readMsg(e.data);
      if (m.type !== "Results") return;
      const t = (m.channel?.alternatives?.[0]?.transcript || "").trim();
      if (m.is_final) { if (t) this.finals.push(t); this.partial = ""; } else this.partial = t;
      this.onText();
    });
    ws.keep = setInterval(() => { if (ws.readyState === 1 && !this.active) ws.send(JSON.stringify({ type: "KeepAlive" })); }, 4000);
    return ws;
  }

  write(ws, pcm) { ws.send(pcm); }

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
      inputAudioTranscription: { languageCodes: [cfg.language], customVocabulary: hints.slice(0, 100) } } }));
    await new Promise((res, rej) => {
      const t = setTimeout(() => rej(new Error("Gemini não respondeu")), 6000);
      ws.onclose = (e) => { clearTimeout(t); rej(new Error(`Gemini recusou a ligação (${e.code}${e.reason ? `: ${e.reason}` : ""})`)); };
      ws.onmessage = async (e) => { const m = await readMsg(e.data); if (m.setupComplete) { clearTimeout(t); res(); } };
    });
    ws.onerror = () => {};
    ws.onmessage = this.own(ws, async (e) => {
      const sc = (await readMsg(e.data)).serverContent;
      if (!sc) return;
      if (sc.inputTranscription) { const t = (sc.inputTranscription.text || "").trim(); if (t) this.finals.push(t); this.partial = ""; }
      else if (sc.interimInputTranscription) this.partial = (sc.interimInputTranscription.text || "").trim();
      else return;
      this.onText();
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
    ws.onmessage = this.own(ws, async (e) => {
      const m = await readMsg(e.data);
      if (m.message_type === "partial_transcript") this.partial = m.text || "";
      else if (m.message_type === "committed_transcript") { if (m.text?.trim()) this.finals.push(m.text.trim()); this.partial = ""; }
      else return;
      this.onText();
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
    this.gen++;
    this.prefix = "";
    this.cur = "";
    this.onText();
    try { this.r.abort(); } catch { /* ignorar */ }
    if (!this.closed) this.start();
  }
  close() { this.closed = true; this.gen++; try { this.r.abort(); } catch { /* ignorar */ } }
}

export const hasWebSpeech = () => !!(window.SpeechRecognition || window.webkitSpeechRecognition);

const ENGINES = { deepgram: DeepgramEngine, gemini: GeminiEngine, scribe: ScribeEngine };
const order = () => (localStorage.getItem("ensaio-stt") === "scribe" ? ["scribe", "deepgram", "gemini", "webspeech"] : ["deepgram", "gemini", "webspeech"]);

export class Listener {
  constructor({ onText, onLevel, onNotice, onEngine }) {
    Object.assign(this, { onText, onLevel, onNotice, onEngine, base: "", kind: "none", lastChunkAt: 0, hints: [], tried: new Set() });
    this.emit = () => this.onText([this.base, this.engine?.text() || ""].filter(Boolean).join(" "));
  }

  async open(hints = []) {
    this.hints = hints;
    this.mic = new MicStream();
    await this.mic.open((pcm) => { this.lastChunkAt = performance.now(); this.engine?.send(pcm); }, this.onLevel);
    await this.start([]);
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
  clear(hints) {
    this.hints = hints || this.hints;
    this.base = "";
    this.engine?.clear(this.hints);
    this.emit();
  }

  setActive(on) { this.engine?.setActive(on); }
  close() { this.engine?.close(); this.mic?.close(); }
}
