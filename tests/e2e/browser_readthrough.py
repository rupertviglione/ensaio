"""Real-browser read-through tests (Chromium) through the actual app UI.
  fakemic  : Chromium fake device fed from a WAV → checks badge "Escuta: Deepgram" + live transcript.
  read     : full read-through of a character; actor audio (Edge pt-PT, optional distortion) injected as the mic stream
             when the app is listening; reports false errors in the final report.
Usage: python tests/browser_readthrough.py fakemic
       python tests/browser_readthrough.py read [deepgram|gemini] [clean|distorted] [SCRIPT_TITLE] [CHARACTER]
"""
import asyncio
import base64
import json
import subprocess
import sys
import time

import edge_tts
import httpx
import imageio_ffmpeg
from playwright.async_api import async_playwright

URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
API = URL + "/api"
FF = imageio_ffmpeg.get_ffmpeg_exe()
ACTOR_VOICE = {"female": "pt-PT-RaquelNeural", "male": "pt-PT-DuarteNeural"}

INJECT = """
(() => {
  const ctx = new AudioContext();
  const dest = ctx.createMediaStreamDestination();
  const noise = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
  const d = noise.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * 0.002;
  const n = ctx.createBufferSource(); n.buffer = noise; n.loop = true; n.connect(dest); n.start();
  navigator.mediaDevices.getUserMedia = async () => { await ctx.resume(); return dest.stream; };
  window.__say = async (b64) => {
    await ctx.resume();
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const buf = await ctx.decodeAudioData(bytes.buffer);
    const src = ctx.createBufferSource(); src.buffer = buf; src.connect(dest); src.start();
    // ground truth: moment the actor's voice really ends (last sample above -40 dBFS)
    const ch = buf.getChannelData(0); let k = ch.length - 1; while (k > 0 && Math.abs(ch[k]) < 0.01) k--;
    (window.__speechEnds = window.__speechEnds || []).push([performance.now(), performance.now() + (k / buf.sampleRate) * 1000]);
    return buf.duration;
  };
})();
"""


def say_text(text: str) -> str:
    import re
    return re.sub(r"\([^)]*\)", " ", text)


async def actor_audio(text: str, voice: str, distorted: bool) -> bytes:
    for attempt in range(4):
        try:
            return await _actor_audio(text, voice, distorted)
        except Exception:
            if attempt == 3:
                raise
            await asyncio.sleep(1 + attempt)


async def _actor_audio(text: str, voice: str, distorted: bool) -> bytes:
    mp3 = bytearray()
    async for c in edge_tts.Communicate(say_text(text), voice, rate="+6%" if distorted else "-4%", pitch="-6Hz" if distorted else "+0Hz").stream():
        if c["type"] == "audio":
            mp3.extend(c["data"])
    if not distorted:
        return bytes(mp3)
    # light distortion: telephone band, pink noise, slight tempo change, lower level
    cmd = [FF, "-loglevel", "error", "-i", "pipe:0", "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.03:sample_rate=24000",
           "-filter_complex", "[0:a]atempo=1.05,highpass=f=250,lowpass=f=3300,volume=0.8[v];[v][1:a]amix=inputs=2:duration=first:weights=1 0.6",
           "-f", "mp3", "pipe:1"]
    return subprocess.run(cmd, input=bytes(mp3), capture_output=True, check=True).stdout


async def fakemic():
    async with httpx.AsyncClient(timeout=60) as c:
        demo = next(s for s in (await c.get(f"{API}/scripts")).json() if s["title"] == "A Espera")
        sc = (await c.get(f"{API}/scripts/{demo['id']}")).json()
        line = next(ln for ln in sc["lines"] if ln["character"] == "MARTA")
        sess = (await c.post(f"{API}/sessions", json={"script_id": demo["id"], "character": "MARTA", "start_idx": line["idx"]})).json()
    mp3 = await actor_audio(line["text"], ACTOR_VOICE["female"], False)
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "2", "/root/sil.wav"], check=True)
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", "pipe:0", "-ar", "48000", "-ac", "1", "/root/line.wav"], input=mp3, check=True)
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", "/root/sil.wav", "-i", "/root/line.wav", "-i", "/root/sil.wav", "-i", "/root/sil.wav",
                    "-filter_complex", "concat=n=4:v=0:a=1", "/root/fake_mic.wav"], check=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/root/bin/chromium", args=[
            "--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            "--use-file-for-fake-audio-capture=/root/fake_mic.wav", "--autoplay-policy=no-user-gesture-required"])
        ctx = await b.new_context(permissions=["microphone"])
        page = await ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(m.text))
        await page.goto(f"{URL}/ensaio/{sess['id']}")
        await page.get_by_test_id("play-btn").click()
        t0 = time.time()
        badge, live = "", ""
        while time.time() - t0 < 25:
            await asyncio.sleep(0.5)
            badge = await page.get_by_test_id("stt-engine-name").inner_text()
            if await page.get_by_test_id("live-transcript").count():
                live = await page.get_by_test_id("live-transcript").inner_text()
            if "Deepgram" in badge and len(live.split()) > 6:
                break
        print("BADGE:", badge)
        print("LIVE :", live)
        print("ESPERADO:", line["text"])
        print("console:", [x for x in logs if "deepgram" in x.lower() or "motor" in x.lower()][:6])
        await b.close()


async def read(engine: str, mode: str, title: str, character: str):
    async with httpx.AsyncClient(timeout=120) as c:
        scr = next(s for s in (await c.get(f"{API}/scripts")).json() if s["title"] == title)
        sc = (await c.get(f"{API}/scripts/{scr['id']}")).json()
        sess = (await c.post(f"{API}/sessions", json={"script_id": scr["id"], "character": character, "strictness": "grave"})).json()
    lines = sc["lines"]
    voice = ACTOR_VOICE["female" if character.split()[0].endswith("A") else "male"]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/root/bin/chromium", args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        ctx = await b.new_context()
        await ctx.add_init_script(INJECT)
        await ctx.add_init_script(f"localStorage.setItem('ensaio-stt', '{engine}');")
        page = await ctx.new_page()
        page.on("console", lambda m: ("ensaio" in m.text or "deepgram" in m.text.lower()) and print("   console:", m.text[:160]))
        await page.goto(f"{URL}/ensaio/{sess['id']}")
        await page.get_by_test_id("play-btn").click()
        done_blocks, t_end = set(), time.time() + 600
        last_dbg = 0
        while time.time() < t_end:
            await asyncio.sleep(0.3)
            if await page.get_by_test_id("continue-btn").count():
                print("   ! interrompido pela IA → Continuar")
                await page.get_by_test_id("continue-btn").click()
                continue
                last_dbg = time.time()
                st = await page.get_by_test_id("rehearsal-status").inner_text() if await page.get_by_test_id("rehearsal-status").count() else "?"
                print("   estado:", st, "| bloco:", await page.get_by_test_id("current-line-text").get_attribute("data-block-idxs") if await page.get_by_test_id("current-line-text").count() else "")
            if await page.get_by_test_id("done-speaking-btn").count() == 0:
                if done_blocks and await page.get_by_test_id("play-btn").count():
                    break
                continue
            raw = await page.get_by_test_id("current-line-text").get_attribute("data-block-idxs") if await page.get_by_test_id("current-line-text").count() else ""
            ids = [int(x) for x in (raw or "").split(",") if x]
            if not ids or ids[0] in done_blocks:
                continue
            done_blocks.add(ids[0])
            text = " ".join(lines[k]["edited_text"] or lines[k]["text"] for k in ids)
            badge = await page.get_by_test_id("stt-engine-name").inner_text()
            dur = await page.evaluate("b => window.__say(b)", base64.b64encode(await actor_audio(text, voice, mode == "distorted")).decode())
            t0 = time.time()
            while time.time() - t0 < dur + 6 and await page.get_by_test_id("done-speaking-btn").count():
                await asyncio.sleep(0.3)
            manual = False
            if await page.get_by_test_id("done-speaking-btn").count():
                await page.get_by_test_id("done-speaking-btn").click()
                manual = True
            print(f"[{ids}] {badge} {'(Terminei)' if manual else '(fim detectado)'}: {text[:70]}")
            if ids[-1] >= max(ln["idx"] for ln in lines if ln["character"] == character):
                await asyncio.sleep(4)
                break
        ends = await page.evaluate("window.__speechEnds || []")
        lat = [e for e in await page.evaluate("window.__ensaioLatency || []") if e.get("type") == "actorEnd→aiStart"]
        real = []
        for e in lat:
            prev = [end for push, end in ends if push < e["at"]]
            r = round(e["at"] - prev[-1]) if prev else None
            real.append(r)
            print(f"   LAT linha {e['line']} {e.get('engine')}: real={r}ms vad={e['ms_voice_to_audio']} detect={e['ms_voice_to_detect']} match→áudio={e['ms_match_to_audio']}")
        ok = [r for r in real if r is not None]
        if ok:
            ok.sort()
            print(f"LATÊNCIA {engine}/{mode}: n={len(ok)} mediana={ok[len(ok)//2]}ms p90={ok[int(len(ok)*0.9) - (1 if len(ok) > 1 else 0)]}ms max={ok[-1]}ms")
        await b.close()
    async with httpx.AsyncClient(timeout=180) as c:
        fin = (await c.post(f"{API}/sessions/{sess['id']}/finish")).json()
    for t in fin["turns"]:
        print(f"  fala {t['line_idxs']}: ouvido={t['said']!r}")
        for d in t["differences"]:
            print(f"     cand {d['status']:9} {d['expected']!r} → {d['said']!r}  {d.get('note', '')[:90]}")
    sm = fin["summary"]
    print(f"\nRESULTADO {engine}/{mode} {title}/{character}: blocos={len(fin['turns'])} erros_falsos_no_relatório={len(sm['differences'])} "
          f"descartadas={sm['stats']['discarded']} score={sm['score']}")


if __name__ == "__main__":
    if sys.argv[1] == "fakemic":
        asyncio.run(fakemic())
    else:
        a = sys.argv[2:] + [None] * 4
        asyncio.run(read(a[0] or "deepgram", a[1] or "clean", a[2] or "A Espera", a[3] or "MARTA"))
