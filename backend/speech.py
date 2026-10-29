import os
import logging
import datetime

import httpx
from fastapi import HTTPException

log = logging.getLogger("ensaio.stt")

DEEPGRAM_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DEEPGRAM_MODEL = os.environ.get("DEEPGRAM_MODEL", "nova-3")
GEMINI_LIVE_MODEL = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.5-transcribe-live")
DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"
GEMINI_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained"


def missing(engine: str) -> str:
    return f"Falta a chave {engine} no ficheiro backend/.env"


def messages() -> list:
    out = []
    if not DEEPGRAM_KEY:
        out.append(missing("Deepgram"))
    if not GEMINI_KEY:
        out.append(missing("Gemini"))
    return out


async def deepgram_token() -> dict:
    if not DEEPGRAM_KEY:
        raise HTTPException(503, missing("Deepgram"))
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post("https://api.deepgram.com/v1/auth/grant", headers={"Authorization": f"Token {DEEPGRAM_KEY}"},
                             json={"ttl_seconds": 120})
    except httpx.HTTPError as e:
        log.warning("Deepgram grant falhou: %s", e)
        raise HTTPException(503, "Deepgram indisponível (rede).")
    if r.status_code in (401, 403):
        raise HTTPException(503, "Chave Deepgram inválida ou sem permissão (backend/.env).")
    if r.status_code == 402:
        raise HTTPException(503, "Sem crédito Deepgram.")
    if r.status_code >= 400:
        log.warning("Deepgram grant %s: %s", r.status_code, r.text[:200])
        raise HTTPException(503, f"Deepgram indisponível ({r.status_code}).")
    params = {"model": DEEPGRAM_MODEL, "language": "pt-PT", "encoding": "linear16", "sample_rate": 16000, "channels": 1,
              "interim_results": "true", "punctuate": "true", "smart_format": "false", "endpointing": 400}
    return {"token": r.json()["access_token"], "url": DEEPGRAM_URL, "params": params}


async def gemini_token() -> dict:
    if not GEMINI_KEY:
        raise HTTPException(503, missing("Gemini"))
    from google import genai
    client = genai.Client(api_key=GEMINI_KEY, http_options={"api_version": "v1alpha"})
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    try:
        tok = await client.aio.auth_tokens.create(config={
            "uses": 1, "expire_time": now + datetime.timedelta(minutes=30),
            "new_session_expire_time": now + datetime.timedelta(minutes=1),
            "live_connect_constraints": {"model": GEMINI_LIVE_MODEL}})
    except Exception as e:
        msg = str(e)
        log.warning("token Gemini falhou: %s", msg[:300])
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            raise HTTPException(503, "Quota grátis do Gemini esgotada.")
        if "401" in msg or "403" in msg or "API_KEY" in msg.upper():
            raise HTTPException(503, "Chave Gemini inválida (backend/.env).")
        raise HTTPException(503, "Gemini indisponível.")
    return {"token": tok.name, "url": GEMINI_URL, "model": GEMINI_LIVE_MODEL, "language": "pt-PT"}
