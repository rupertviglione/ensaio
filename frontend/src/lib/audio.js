const player = new Audio();
player.preload = "auto";

export function stopAudio() {
  player.pause();
  player.onended = null;
  player.onerror = null;
  player.onplaying = null;
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

export const audioProgress = () => (player.duration > 0 && !player.paused ? player.currentTime / player.duration : 0);
