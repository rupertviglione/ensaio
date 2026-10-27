"""Manual check: streams TTS PCM (16 kHz) into Scribe v2 Realtime via the app's token endpoint, like the browser does."""
import asyncio
import base64
import json
import os
import sys
import time

import httpx
import websockets

API = os.environ.get("API_URL", "http://localhost:8001/api")
KEY = os.environ["ELEVENLABS_API_KEY"]
TEXT = sys.argv[1] if len(sys.argv) > 1 else "Perdi-o. Ou melhor, deixei-o ir. Fiquei a vê-lo afastar-se e não me mexi."
VOICE = "bBNhdwrIjl4fcVYiRbT2"


async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        pcm = (await c.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}", params={"output_format": "pcm_16000"},
                            headers={"xi-api-key": KEY}, json={"text": TEXT, "model_id": "eleven_multilingual_v2", "language_code": "pt"})).content
        cfg = (await c.post(f"{API}/stt/token")).json()
    url = f"{cfg['url']}?model_id={cfg['model_id']}&token={cfg['token']}&audio_format=pcm_16000&language_code=pt&commit_strategy=manual"
    async with websockets.connect(url) as ws:
        sent_at = {}
        t0 = time.perf_counter()

        async def sender():
            for i in range(0, len(pcm), 3200):
                await ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": base64.b64encode(pcm[i:i + 3200]).decode(),
                                          "commit": False, "sample_rate": 16000}))
                sent_at[i // 3200] = time.perf_counter()
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.8)
            await ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": "", "commit": True, "sample_rate": 16000}))

        task = asyncio.create_task(sender())
        audio_s = len(pcm) / 32000
        while True:
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
            except asyncio.TimeoutError:
                break
            el = time.perf_counter() - t0
            print(f"{el:6.2f}s (áudio enviado {min(el, audio_s):5.2f}s) {m.get('message_type')}: {m.get('text', m)}")
            if m.get("message_type") == "committed_transcript":
                break
        await task
        print(f"duração do áudio {audio_s:.2f}s; fim do envio ~{audio_s:.2f}s")


asyncio.run(main())
