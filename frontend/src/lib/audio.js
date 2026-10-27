const player = new Audio();

export function stopAudio() {
  player.pause();
  player.onended = null;
  player.onerror = null;
}

export function playUrl(url) {
  stopAudio();
  return new Promise((resolve) => {
    player.src = url;
    player.onended = () => resolve(true);
    player.onerror = () => resolve(false);
    player.play().catch(() => resolve(false));
  });
}

export class Recorder {
  async init() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.resume();
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    src.connect(this.analyser);
  }

  record({ onLevel, silenceMs = 1600, noSpeechMs = 15000, maxMs = 120000, threshold = 0.018 } = {}) {
    return new Promise((resolve) => {
      const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4";
      const mr = new MediaRecorder(this.stream, { mimeType: mime });
      const chunks = [];
      const buf = new Float32Array(this.analyser.fftSize);
      const start = performance.now();
      let spoke = false;
      let lastVoice = start;
      let raf;
      let mode = "auto";
      mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      mr.onstop = () => {
        cancelAnimationFrame(raf);
        onLevel?.(0);
        if (mode === "cancel" || (!spoke && mode === "auto")) return resolve(null);
        resolve(new Blob(chunks, { type: mime }));
      };
      this._stop = (m) => {
        mode = m;
        if (mr.state !== "inactive") mr.stop();
      };
      const tick = () => {
        this.analyser.getFloatTimeDomainData(buf);
        let s = 0;
        for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
        const rms = Math.sqrt(s / buf.length);
        onLevel?.(rms);
        const t = performance.now();
        if (rms > threshold) {
          spoke = true;
          lastVoice = t;
        }
        if ((spoke && t - lastVoice > silenceMs) || t - start > maxMs || (!spoke && t - start > noSpeechMs)) {
          this._stop("auto");
          return;
        }
        raf = requestAnimationFrame(tick);
      };
      mr.start(250);
      tick();
    });
  }

  stop() {
    this._stop?.("manual");
  }

  cancel() {
    this._stop?.("cancel");
  }

  destroy() {
    this.cancel();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
  }
}
