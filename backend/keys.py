"""API keys set in the app (Definições). Stored in Mongo; they take precedence over backend/.env. Never returned to the browser."""
import logging
import os

import eleven
import speech

log = logging.getLogger("ensaio.keys")

ENV = {"elevenlabs": "ELEVENLABS_API_KEY", "deepgram": "DEEPGRAM_API_KEY", "gemini": "GEMINI_API_KEY"}
LABEL = {"elevenlabs": "ElevenLabs", "deepgram": "Deepgram", "gemini": "Gemini"}
SOURCE: dict = {}
STATUS: dict = {}


def current(p: str) -> str:
    return {"elevenlabs": eleven.KEY, "deepgram": speech.DEEPGRAM_KEY, "gemini": speech.GEMINI_KEY}[p]


def apply(p: str, key: str):
    key = (key or "").strip()
    if p == "elevenlabs":
        eleven.set_key(key)
    elif p == "deepgram":
        speech.DEEPGRAM_KEY = key
    else:
        speech.GEMINI_KEY = key


async def validate(p: str, key: str) -> dict:
    try:
        if p == "deepgram":
            return await speech.validate_deepgram(key)
        if p == "gemini":
            return await speech.validate_gemini(key)
        return await validate_eleven(key)
    except Exception as e:
        log.warning("validação %s falhou: %s", p, e)
        return {"valid": False, "message": f"Não consegui validar a chave {LABEL[p]} ({str(e)[:80]})."}


async def validate_eleven(key: str) -> dict:
    """Checks a candidate ElevenLabs key with its own client (never touches the key in use)."""
    import httpx
    h = {"xi-api-key": key}
    async with httpx.AsyncClient(base_url=eleven.BASE, timeout=15, headers=h) as c:
        u = await c.get("/v1/user")
        body = u.text
        if u.status_code == 401 and "invalid_api_key" in body:
            return {"valid": False, "message": "Chave ElevenLabs inválida (usa a chave secreta sk_…, não o ID)."}
        out = {"valid": True, "permissions": {}}
        if u.status_code == 200:
            sub = u.json().get("subscription") or {}
            out.update(character_count=sub.get("character_count"), character_limit=sub.get("character_limit"), tier=sub.get("tier"))
        else:
            out["credits_error"] = "sem permissão para ler os créditos (User: Read)"
        v = await c.get("/v2/voices", params={"page_size": 1})
        out["permissions"]["voices_read"] = v.status_code == 200
        t = await c.post("/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb", params={"output_format": "mp3_22050_32"},
                         json={"text": "Olá.", "model_id": eleven.TTS_MODEL})
        out["permissions"]["tts"] = t.status_code == 200
        if t.status_code == 401 and "invalid_api_key" in t.text:
            return {"valid": False, "message": "Chave ElevenLabs inválida (usa a chave secreta sk_…, não o ID)."}
        out["message"] = "Chave ElevenLabs válida." + ("" if out["permissions"]["tts"] else " Falta a permissão Text to Speech.")
        return out


async def load(db):
    doc = await db.settings.find_one({"_id": "keys"}) or {}
    for p in ENV:
        if doc.get(p):
            apply(p, doc[p])
            SOURCE[p] = "app"
        else:
            SOURCE[p] = "env" if os.environ.get(ENV[p], "").strip() else None


async def save(db, p: str, key: str) -> dict:
    key = (key or "").strip()
    if not key:
        await db.settings.update_one({"_id": "keys"}, {"$unset": {p: ""}}, upsert=True)
        apply(p, os.environ.get(ENV[p], ""))
        SOURCE[p] = "env" if current(p) else None
        STATUS.pop(p, None)
        return public(p)
    st = await validate(p, key)
    if st["valid"]:
        STATUS[p] = st
        await db.settings.update_one({"_id": "keys"}, {"$set": {p: key}}, upsert=True)
        apply(p, key)
        SOURCE[p] = "app"
        log.info("chave %s guardada nas Definições (…%s)", LABEL[p], key[-4:])
    return {**public(p), "attempt": st}


def public(p: str) -> dict:
    k = current(p)
    return {"provider": p, "label": LABEL[p], "configured": bool(k), "source": SOURCE.get(p), "last4": k[-4:] if k else "", "status": STATUS.get(p)}
