import { normTokens, similar } from "./match";

export const cleanForTts = (t) => (t || "").replace(/\([^)]*\)/g, "").replace(/[*_#>~|[\]]/g, "").replace(/\s+/g, " ").trim();
export const splitWords = (t) => (t || "").split(/\s+/).filter(Boolean);
const wordNorm = (w) => normTokens(w).join("");

// Drops words that are the speaker/prompter audio leaking into the mic.
export function removeEcho(words, ref) {
  const r = splitWords(ref).map(wordNorm).filter(Boolean);
  const n = words.map(wordNorm);
  const pos = n.map((w) => (w ? r.reduce((acc, x, j) => (similar(w, x) ? [...acc, j] : acc), []) : []));
  return words.filter((_, i) => {
    if (!n[i]) return false;
    if (!pos[i].length) return true;
    if (r.length <= 4) return false;
    return !pos[i].some((j) => (pos[i + 1] || []).includes(j + 1) || (pos[i - 1] || []).includes(j - 1));
  });
}

export function alignPos(expWords, said) {
  const e = expWords.map(wordNorm);
  let p = 0;
  said.map(wordNorm).filter(Boolean).forEach((s) => {
    for (let k = p; k < Math.min(e.length, p + 6); k++) if (similar(e[k], s)) { p = k + 1; break; }
  });
  return p;
}

export const firstHint = (expected) => splitWords(cleanForTts(expected)).slice(0, 3).join(" ");

export class TranscriptBuffer {
  constructor() {
    this.words = [];
    this.times = [];
    this.text = "";
    this.start = 0;
    this.windows = [];
    this.lastChange = performance.now();
  }

  update(text) {
    if (text === this.text) return false;
    const now = performance.now();
    const w = splitWords(text);
    this.times = w.map((_, i) => (i < this.words.length ? this.times[i] : now));
    this.words = w;
    this.text = text;
    this.lastChange = now;
    return true;
  }

  reset() {
    this.start = this.words.length;
    this.windows = [];
  }

  // Block boundary: forget everything; remember the previous block's tail to drop it if it reappears (late finals).
  clear() {
    const prev = this.turnWords();
    this.prevTail = prev.slice(-12).map(wordNorm).filter(Boolean);
    this.words = [];
    this.times = [];
    this.text = "";
    this.start = 0;
    this.windows = [];
    this.lastChange = performance.now();
  }

  dropRepeat(out) {
    const p = this.prevTail || [];
    const n = out.map(wordNorm);
    for (let k = Math.min(p.length, n.length); k >= 2; k--) {
      const tail = p.slice(-k);
      if (tail.every((w, i) => similar(w, n[i]))) return out.slice(k);
    }
    return out;
  }

  echoStart(ref, tailMs = 0) {
    this.windows.push({ ref, t0: performance.now(), t1: Infinity, tailMs });
  }

  echoEnd(settle = 500) {
    const w = this.windows[this.windows.length - 1];
    if (w && w.t1 === Infinity) { w.end = performance.now(); w.t1 = w.end + settle; }
  }

  turnWords() {
    const out = [];
    let run = [];
    let runWin = null;
    const flush = () => { if (run.length) out.push(...removeEcho(run, runWin.ref)); run = []; runWin = null; };
    for (let i = this.start; i < this.words.length; i++) {
      const t = this.times[i];
      const win = this.windows.find((w) => t >= w.t0 && t <= w.t1) || null;
      if (win !== runWin) flush();
      if (!win) { out.push(this.words[i]); continue; }
      if (win.tailMs && win.end !== undefined && t < win.end - win.tailMs) continue;
      runWin = win;
      run.push(this.words[i]);
    }
    flush();
    return this.dropRepeat(out);
  }

  lastWordAt() {
    return this.times[this.times.length - 1] ?? 0;
  }
}
