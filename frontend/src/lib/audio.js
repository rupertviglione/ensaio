const player = new Audio();
player.preload = "auto";

// Rehearsal playback: pre-decoded AudioBuffers on a Web Audio context (no fetch/decode at the cue).
let ctx = null;
let cur = null;
const out = () => (ctx ||= new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive" }));
export const unlockAudio = () => out().resume().catch(() => {});
export const outputLatencyMs = () => (ctx ? Math.round(((ctx.baseLatency || 0) + (ctx.outputLatency || 0)) * 1000) : 0);

export async function loadClip(url) {
  if (!url) return null;
  try {
    const data = await (await fetch(url)).arrayBuffer();
    return { url, buf: await out().decodeAudioData(data) };
  } catch {
    return { url, buf: null };
  }
}

export function playClip(clip, onStart) {
  if (!clip) return Promise.resolve(false);
  if (!clip.buf || out().state !== "running") return playUrl(clip.url, onStart);
  stopAudio();
  return new Promise((resolve) => {
    const src = out().createBufferSource();
    src.buffer = clip.buf;
    src.connect(out().destination);
    cur = { src, start: out().currentTime, dur: clip.buf.duration };
    src.onended = () => { if (cur?.src === src) cur = null; resolve(true); };
    src.start();
    onStart?.();
  });
}

export function stopAudio() {
  player.pause();
  player.onended = null;
  player.onerror = null;
  player.onplaying = null;
  if (cur) { const { src } = cur; cur = null; src.onended = null; try { src.stop(); } catch { /* parado */ } }
}

export function playUrl(url, onStart) {
  stopAudio();
  return new Promise((resolve) => {
    player.src = url;
    player.onplaying = () => { player.onplaying = null; onStart?.(); };
    player.onended = () => resolve(true);
    player.onerror = () => resolve(false);
    player.play().catch(() => resolve(false));
  });
}

export const audioProgress = () => {
  if (cur) return Math.min(1, (out().currentTime - cur.start) / cur.dur);
  return player.duration > 0 && !player.paused ? player.currentTime / player.duration : 0;
};
