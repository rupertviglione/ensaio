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

const SCRIBE_FATAL = new Set(["auth_error", "quota_exceeded", "unaccepted_terms"]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function b64(buf) {
  const u = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return btoa(s);
}

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

// ElevenLabs Scribe v2 Realtime over WebSocket, manual commits, reconnect keeps the captured text.
class ScribeEngine {
  constructor(onText, onFatal) {
    Object.assign(this, { onText, onFatal, committed: [], partial: "", queue: [], active: true, closed: false, fails: 0 });
  }

  text() {
    return [...this.committed, this.partial].filter(Boolean).join(" ");
  }

  async connect() {
    const cfg = await api.sttToken();
    const q = new URLSearchParams({ model_id: cfg.model_id, token: cfg.token, audio_format: "pcm_16000", language_code: cfg.language_code, commit_strategy: "manual" });
    const ws = new WebSocket(`${cfg.url}?${q}`);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("Ligação Scribe falhou")); });
    this.ws = ws;
    ws.onmessage = (e) => this.onMsg(JSON.parse(e.data));
    ws.onerror = () => {};
    ws.onclose = (e) => {
      if (this.ws !== ws) return;
      this.ws = null;
      console.warn("[scribe] ligação fechada", e.code, e.reason);
      if (!this.closed && this.active) this.reconnect();
    };
    this.fails = 0;
    while (this.queue.length) ws.send(this.queue.shift());
  }

  onMsg(m) {
    const t = m.message_type;
    if (t === "partial_transcript") { this.partial = m.text || ""; this.onText(); }
    else if (t === "committed_transcript") {
      if (m.text?.trim()) this.committed.push(m.text.trim());
      this.partial = "";
      this.onText();
    } else if (t !== "session_started") {
      console.warn("[scribe]", t, m.error || m.warning || "");
      if (SCRIBE_FATAL.has(t)) { this.closed = true; this.onFatal(new Error(`Scribe: ${t}`)); }
    }
  }

  async reconnect() {
    if (this.partial) { this.committed.push(this.partial); this.partial = ""; }
    if (this.reconnecting) return;
    this.reconnecting = true;
    while (!this.closed && this.active) {
      try { await this.connect(); console.info("[scribe] religado"); break; } catch (e) {
        if (++this.fails >= 4) { this.closed = true; this.onFatal(e); break; }
        await sleep(400 * this.fails);
      }
    }
    this.reconnecting = false;
  }

  send(pcm) {
    if (!this.active || this.closed) return;
    const msg = JSON.stringify({ message_type: "input_audio_chunk", audio_base_64: b64(pcm), commit: false, sample_rate: 16000 });
    if (this.ws?.readyState === 1) this.ws.send(msg);
    else { this.queue.push(msg); if (this.queue.length > 150) this.queue.shift(); }
  }

  commit() {
    if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ message_type: "input_audio_chunk", audio_base_64: "", commit: true, sample_rate: 16000 }));
  }

  setActive(on) {
    this.active = on;
    if (on && !this.ws && !this.closed) this.reconnect();
  }

  close() {
    this.closed = true;
    this.ws?.close();
  }
}

// Previous engine (browser Web Speech), used when the ElevenLabs key cannot issue Scribe tokens.
class WebSpeechEngine {
  constructor(onText) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    Object.assign(this, { onText, prefix: "", cur: "", closed: false, active: true });
    const r = new SR();
    r.lang = "pt-PT";
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e) => {
      let t = "";
      for (let i = 0; i < e.results.length; i++) t += `${e.results[i][0].transcript} `;
      this.cur = t.trim();
      this.onText();
    };
    r.onerror = () => {};
    r.onend = () => {
      this.prefix = this.text();
      this.cur = "";
      if (!this.closed && this.active) try { r.start(); } catch { /* já activo */ }
    };
    this.r = r;
    r.start();
  }

  text() { return `${this.prefix} ${this.cur}`.trim(); }
  send() {}
  commit() {}
  setActive(on) {
    this.active = on;
    if (on && !this.closed) try { this.r.start(); } catch { /* já activo */ }
  }
  close() { this.closed = true; try { this.r.abort(); } catch { /* ignorar */ } }
}

export const hasWebSpeech = () => !!(window.SpeechRecognition || window.webkitSpeechRecognition);

export class Listener {
  constructor({ onText, onLevel, onNotice, onEngine }) {
    Object.assign(this, { onText, onLevel, onNotice, onEngine, base: "", kind: "none", lastChunkAt: 0 });
    this.emit = () => this.onText([this.base, this.engine?.text() || ""].filter(Boolean).join(" "));
  }

  async open() {
    this.mic = new MicStream();
    await this.mic.open((pcm) => { this.lastChunkAt = performance.now(); this.engine?.send(pcm); }, this.onLevel);
    const e = new ScribeEngine(this.emit, (err) => this.fallback(err));
    this.engine = e;
    try {
      await e.connect();
      this.setKind("scribe");
    } catch (err) {
      this.fallback(err);
    }
  }

  setKind(k) { this.kind = k; this.onEngine?.(k); }

  fallback(err) {
    const msg = errMsg(err);
    console.warn("[ensaio] Scribe indisponível, a usar o motor anterior:", msg);
    this.base = [this.base, this.engine?.text() || ""].filter(Boolean).join(" ");
    this.engine?.close();
    this.engine = null;
    this.onNotice?.(msg);
    if (hasWebSpeech()) {
      try { this.engine = new WebSpeechEngine(this.emit); this.setKind("webspeech"); return; } catch { /* sem reconhecimento */ }
    }
    this.setKind("none");
  }

  commit() { this.engine?.commit(); }
  setActive(on) { this.engine?.setActive(on); }
  close() { this.engine?.close(); this.mic?.close(); }
}
