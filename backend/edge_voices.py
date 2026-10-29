import asyncio
import logging

import edge_tts

log = logging.getLogger("ensaio.edge")

VOICES = [
    {"id": "pt-PT-RaquelNeural", "name": "Raquel", "gender": "female"},
    {"id": "pt-PT-DuarteNeural", "name": "Duarte", "gender": "male"},
]
# (pitch Hz, rate %) per voice: each character gets a distinct combination.
PALETTE = [(0, 0), (-12, -6), (10, 6), (-22, -10), (18, -4), (-6, 10), (24, 8), (-30, 4)]
PROMPTER = {"edge_voice": "pt-PT-RaquelNeural", "edge_pitch": 4, "edge_rate": 12}
SEM = asyncio.Semaphore(4)


async def refresh_voices():
    try:
        found = [v for v in await edge_tts.list_voices() if v.get("Locale") == "pt-PT"]
    except Exception as e:
        log.warning("lista de vozes Edge falhou: %s", e)
        return VOICES
    if found:
        VOICES[:] = [{"id": v["ShortName"], "name": v["ShortName"].split("-")[2].replace("Neural", ""),
                      "gender": v.get("Gender", "").lower()} for v in found]
    return VOICES


def ids() -> set:
    return {v["id"] for v in VOICES}


def combos(gender: str) -> list:
    own = [v["id"] for v in VOICES if v["gender"] == gender] or [VOICES[0]["id"]]
    other = [v["id"] for v in VOICES if v["id"] not in own]
    prompter = (PROMPTER["edge_voice"], PROMPTER["edge_pitch"], PROMPTER["edge_rate"])
    out = [(vid, p, r) for p, r in PALETTE for vid in own] + [(vid, p, r) for p, r in PALETTE for vid in other]
    return [c for c in out if c != prompter]


def fmt(pitch: int, rate: int) -> tuple:
    return f"{int(pitch):+d}Hz", f"{int(rate):+d}%"


async def synth(text: str, voice: str, pitch: int = 0, rate: int = 0) -> bytes:
    p, r = fmt(pitch, rate)

    async def run():
        out = bytearray()
        async for chunk in edge_tts.Communicate(text, voice, rate=r, pitch=p).stream():
            if chunk["type"] == "audio":
                out.extend(chunk["data"])
        if not out:
            raise RuntimeError("Edge TTS sem áudio")
        return bytes(out)

    async with SEM:
        for attempt in range(2):
            try:
                return await asyncio.wait_for(run(), timeout=25)
            except Exception as e:
                if attempt:
                    raise
                log.warning("Edge TTS falhou (%s), nova tentativa", e)
