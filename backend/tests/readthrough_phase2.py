"""Phase 2 automated read-through: synthesised correct audio (Edge pt-PT) → Deepgram / Gemini streaming → /turn → report.
Usage: python tests/readthrough_phase2.py [deepgram|gemini] [CHARACTER]"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import time

import edge_tts
import httpx
import imageio_ffmpeg
import websockets

API = os.environ.get("API_URL", "http://localhost:8001") + "/api"
ENGINE = sys.argv[1] if len(sys.argv) > 1 else "deepgram"
CHAR = sys.argv[2] if len(sys.argv) > 2 else "MARTA"
VOICE = {"MARTA": "pt-PT-RaquelNeural"}.get(CHAR, "pt-PT-DuarteNeural")
CH = 3200


async def pcm_for(text: str) -> bytes:
    mp3 = bytearray()
    async for c in edge_tts.Communicate(text, VOICE, rate="-5%").stream():
        if c["type"] == "audio":
            mp3.extend(c["data"])
    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "s16le", "pipe:1"],
                         input=bytes(mp3), capture_output=True, check=True).stdout
    return out + b"\x00" * 16000  # 0.5 s silence


def hints(text: str) -> list:
    words = [w.strip(".,!?;:").lower() for w in text.split()]
    return list(dict.fromkeys(w for w in words if len(w.replace("-", "")) >= 3))


async def deepgram(c: httpx.AsyncClient, pcm: bytes, terms: list) -> str:
    cfg = (await c.post(f"{API}/stt/deepgram-token")).json()
    q = "&".join([f"{k}={v}" for k, v in cfg["params"].items()] + [f"keyterm={httpx.QueryParams({'k': t})['k']}" for t in terms[:40]])
    finals = []
    async with websockets.connect(f"{cfg['url']}?{httpx.QueryParams(q)}", subprotocols=["bearer", cfg["token"]]) as ws:
        async def send():
            for i in range(0, len(pcm), CH):
                await ws.send(pcm[i:i + CH])
                await asyncio.sleep(0.05)
            await ws.send(json.dumps({"type": "Finalize"}))
            await asyncio.sleep(1.2)
            await ws.send(json.dumps({"type": "CloseStream"}))
        t = asyncio.create_task(send())
        async for m in ws:
            d = json.loads(m)
            if d.get("type") == "Results" and d["is_final"]:
                tx = d["channel"]["alternatives"][0]["transcript"].strip()
                if tx:
                    finals.append(tx)
        await t
    return " ".join(finals)


async def gemini(c: httpx.AsyncClient, pcm: bytes, terms: list) -> str:
    cfg = (await c.post(f"{API}/stt/gemini-token")).json()
    finals = []
    async with websockets.connect(f"{cfg['url']}?access_token={cfg['token']}") as ws:
        await ws.send(json.dumps({"setup": {"model": f"models/{cfg['model']}", "generationConfig": {"responseModalities": ["TEXT"]},
                                            "inputAudioTranscription": {"languageCodes": [cfg["language"]], "customVocabulary": terms[:100]}}}))
        await ws.recv()
        for i in range(0, len(pcm), CH):
            await ws.send(json.dumps({"realtimeInput": {"audio": {"data": base64.b64encode(pcm[i:i + CH]).decode(), "mimeType": "audio/pcm;rate=16000"}}}))
            await asyncio.sleep(0.05)
        await ws.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))
        t0 = time.time()
        while time.time() - t0 < 6:
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), 6 - (time.time() - t0)))
            except asyncio.TimeoutError:
                break
            sc = m.get("serverContent", {})
            if sc.get("inputTranscription", {}).get("text"):
                finals.append(sc["inputTranscription"]["text"].strip())
                break
    return " ".join(finals)


async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        demo = next(s for s in (await c.get(f"{API}/scripts")).json() if s["title"] == "A Espera")
        script = (await c.get(f"{API}/scripts/{demo['id']}")).json()
        sess = (await c.post(f"{API}/sessions", json={"script_id": demo["id"], "character": CHAR, "strictness": "grave"})).json()
        mine = [ln for ln in script["lines"] if ln["kind"] == "dialogue" and ln["character"] == CHAR]
        stt = deepgram if ENGINE == "deepgram" else gemini
        for ln in mine:
            text = ln["edited_text"] or ln["text"]
            heard = await stt(c, await pcm_for(text), hints(text))
            r = (await c.post(f"{API}/sessions/{sess['id']}/turn", json={"line_idx": ln["idx"], "line_idxs": [ln["idx"]], "said": heard, "mode": "voz"})).json()
            print(f"[{ln['idx']}] {text}\n     ouvido: {heard}\n     acc={r['turn']['accuracy']} advance={r['advance']} candidatos={[(d['expected'], d['said']) for d in r['turn']['differences']]}")
        fin = (await c.post(f"{API}/sessions/{sess['id']}/finish")).json()
        sm = fin["summary"]
        print(f"\nRESULTADO {ENGINE}: score={sm['score']} diferenças_no_relatório={len(sm['differences'])} descartadas={sm['stats']['discarded']}")
        for d in sm["differences"]:
            print("  REAL:", d)


asyncio.run(main())
