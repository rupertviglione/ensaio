import io
import os
import re
import time
import wave
import asyncio
import logging

import httpx

log = logging.getLogger("ensaio.eleven")

KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
BASE = "https://api.elevenlabs.io"
REALTIME_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
REALTIME_MODEL = "scribe_v2_realtime"
TTS_MODEL = os.environ.get("ELEVEN_TTS_MODEL", "eleven_multilingual_v2")
MAX_CHARS = 2400
PROBE_VOICE = "JBFqnCBsd6RMkjVDRZzb"
INVALID_CODES = {"invalid_api_key", "api_key_id_used_as_api_key", "not_logged_in"}

FUNCTIONS = {
    "tts": "síntese de voz (Text to Speech)",
    "stt": "reconhecimento de voz (Speech to Text)",
    "voices_read": "ler vozes (Voices: Read)",
    "shared_voices": "biblioteca de vozes partilhadas (Voices: Read)",
    "voices_write": "adicionar vozes à conta (Voices: Write)",
    "realtime_token": "transcrição em tempo real (Single-use tokens / Scribe Realtime)",
}

STATUS = {"checked_at": 0.0, "valid": None, "perms": {}, "errors": {}}
STATS = {"elevenlabs": 0, "openai_fallback": 0, "fallback_reasons": []}
_state = {"lang_code": True}
_http: dict = {}
EL_SEM = asyncio.Semaphore(int(os.environ.get("ELEVEN_CONCURRENCY", "3")))


class ElevenError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code or "", message or ""

    @property
    def is_auth(self) -> bool:
        return self.status in (401, 403) or self.code in INVALID_CODES or "permission" in self.message.lower()


def client() -> httpx.AsyncClient:
    if "c" not in _http:
        _http["c"] = httpx.AsyncClient(base_url=BASE, headers={"xi-api-key": KEY}, timeout=httpx.Timeout(90, connect=10))
    return _http["c"]


async def req(method: str, url: str, **kw) -> httpx.Response:
    r = await client().request(method, url, **kw)
    if r.status_code >= 400:
        code, msg = "", r.text[:300]
        try:
            d = r.json().get("detail")
            if isinstance(d, dict):
                code, msg = d.get("status") or d.get("code") or "", d.get("message") or msg
            elif d:
                msg = str(d)[:300]
        except Exception:
            pass
        if code == "invalid_api_key" or "API key ID used" in msg:
            code = "invalid_api_key"
        raise ElevenError(r.status_code, code, msg)
    return r


FALLBACK_TEXT = {
    "tts": "A usar a OpenAI (motor anterior).",
    "stt": "A usar o motor anterior.",
    "realtime_token": "A usar o reconhecimento do browser (motor anterior).",
    "voices_read": "A usar a lista pt-PT verificada.",
    "shared_voices": "A usar a lista pt-PT verificada.",
    "voices_write": "As vozes da biblioteca são usadas directamente.",
}


def perm_message(func: str) -> str:
    if STATUS["valid"] is False:
        return "Chave ElevenLabs inválida (usa a chave secreta sk_…, não o ID da chave). A usar o motor anterior."
    return f"Chave ElevenLabs sem permissão para {FUNCTIONS.get(func, func)}. {FALLBACK_TEXT.get(func, 'A usar o motor anterior.')}"


def messages() -> list:
    if not KEY:
        return ["ElevenLabs não configurada (ELEVENLABS_API_KEY). A usar o motor anterior."]
    if STATUS["valid"] is False:
        return [perm_message("tts")]
    perms = STATUS["perms"]
    return [perm_message(f) for f, ok in perms.items() if ok is False and not (f == "shared_voices" and perms.get("voices_read") is False)]


def can(func: str) -> bool:
    return bool(KEY) and STATUS["perms"].get(func) is not False


def silent_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)
    return buf.getvalue()


async def check_status(force: bool = False) -> dict:
    if not KEY:
        STATUS.update(valid=False, perms={k: False for k in FUNCTIONS}, errors={"key": "sem chave"}, checked_at=time.time())
        return STATUS
    if not force and time.time() - STATUS["checked_at"] < 600:
        return STATUS
    perms, errors = {}, {}

    async def probe(name, coro):
        try:
            r = await coro
            perms[name] = True
            return r
        except ElevenError as e:
            perms[name] = not e.is_auth
            errors[name] = str(e)[:300]
        except Exception as e:
            perms[name] = None
            errors[name] = str(e)[:200]

    await asyncio.gather(
        probe("voices_read", req("GET", "/v2/voices", params={"page_size": 1})),
        probe("shared_voices", req("GET", "/v1/shared-voices", params={"page_size": 1, "language": "pt"})),
        probe("realtime_token", req("POST", "/v1/single-use-token/realtime_scribe")),
    )
    audio = await probe("tts", tts_part("Olá.", PROBE_VOICE))
    await probe("stt", req("POST", "/v1/speech-to-text", data={"model_id": "scribe_v2"},
                           files={"file": ("t.mp3", audio, "audio/mpeg") if audio else ("t.wav", silent_wav(), "audio/wav")}))
    perms["voices_write"] = STATUS["perms"].get("voices_write")
    valid = not any(c in e for e in errors.values() for c in INVALID_CODES)
    STATUS.update(valid=valid, perms=perms, errors=errors, checked_at=time.time())
    log.info("ElevenLabs estado: válida=%s permissões=%s", valid, perms)
    return STATUS


def split_text(text: str, limit: int = MAX_CHARS) -> list:
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?…;:])\s+", text):
        while len(sent) > limit:
            cut = max(sent.rfind(", ", 0, limit), sent.rfind(" ", 0, limit))
            cut = cut if cut > 0 else limit
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(sent[:cut + 1].strip())
            sent = sent[cut + 1:].strip()
        if cur and len(cur) + len(sent) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return parts


async def tts_part(text: str, voice_id: str, previous_text: str = "", next_text: str = "") -> bytes:
    body = {"text": text, "model_id": TTS_MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True}}
    if TTS_MODEL != "eleven_v3":
        body.update({k: v for k, v in (("previous_text", previous_text), ("next_text", next_text)) if v})
    if _state["lang_code"]:
        body["language_code"] = "pt"
    try:
        for wait in (0.6, 1.2, 2.5, 4, 6, 0):
            try:
                async with EL_SEM:
                    r = await req("POST", f"/v1/text-to-speech/{voice_id}", params={"output_format": "mp3_44100_128"}, json=body)
                break
            except ElevenError as e:
                if e.status not in (409, 429) or not wait:
                    raise
                await asyncio.sleep(wait)
    except ElevenError as e:
        if e.status in (400, 422) and "language" in e.message.lower() and _state["lang_code"]:
            _state["lang_code"] = False
            return await tts_part(text, voice_id, previous_text, next_text)
        raise
    return r.content


async def synth(text: str, voice_id: str) -> bytes:
    parts = split_text(text)
    jobs = [tts_part(p, voice_id, parts[i - 1][-300:] if i else "", parts[i + 1][:300] if i + 1 < len(parts) else "")
            for i, p in enumerate(parts)]
    return b"".join(await asyncio.gather(*jobs))


async def realtime_token() -> str:
    r = await req("POST", "/v1/single-use-token/realtime_scribe")
    STATUS["perms"]["realtime_token"] = True
    return r.json()["token"]


PT_STRONG = ("pt-pt", "portugal", "european portuguese", "portuguese (portugal)", "português europeu", "portugues europeu",
             "de portugal", "lisboa", "lisbon", "lisboeta", "european")
BR_WORDS = ("braz", "brasil", "pt-br", "carioca", "paulist", "mineir", "nordest")


def _tags(v: dict) -> str:
    bits = [v.get(k) or "" for k in ("accent", "locale", "description", "name", "descriptive")]
    for lang in v.get("verified_languages") or []:
        if (lang.get("language") or "").startswith("pt"):
            bits += [lang.get("accent") or "", lang.get("locale") or ""]
    return " ".join(str(b) for b in bits).lower()


def is_pt_pt(v: dict) -> bool:
    t = _tags(v)
    return any(k in t for k in PT_STRONG) and not any(k in t for k in BR_WORDS)


async def search_pt_voices() -> list:
    queries = [{"locale": "pt-PT"}, {"accent": "portugal"}, {"accent": "european"}, {"accent": "portuguese"},
               {"search": "portugal"}, {"search": "european portuguese"}, {"search": "lisboa"}, {}]
    found = {}
    for q in queries:
        try:
            r = await req("GET", "/v1/shared-voices", params={"language": "pt", "page_size": 100, **q})
        except ElevenError as e:
            log.warning("shared-voices %s: %s", q, e)
            if e.is_auth:
                raise
            continue
        for v in r.json().get("voices", []):
            if is_pt_pt(v) and v.get("gender") in ("male", "female"):
                found.setdefault(v["voice_id"], v)
    return sorted(found.values(), key=lambda v: -(v.get("cloned_by_count") or 0) - (v.get("usage_character_count_1y") or 0) / 1e5)


async def add_shared(v: dict) -> str:
    name = f"Ensaio {v['name']}"[:40]
    try:
        r = await req("POST", f"/v1/voices/add/{v['public_owner_id']}/{v['voice_id']}", json={"new_name": name})
        STATUS["perms"]["voices_write"] = True
        return r.json().get("voice_id") or v["voice_id"]
    except ElevenError as e:
        if e.is_auth:
            STATUS["perms"]["voices_write"] = False
        log.warning("não adicionei a voz %s (%s)", v["name"], e)
    try:
        r = await req("GET", "/v2/voices", params={"search": name, "page_size": 5})
        mine = [x for x in r.json().get("voices", []) if x.get("name") == name]
        if mine:
            return mine[0]["voice_id"]
    except ElevenError:
        pass
    return v["voice_id"]


async def build_catalog(per_gender: int = 4) -> dict:
    pool = await search_pt_voices()
    if not pool:
        return seed_catalog()
    fem = [v for v in pool if v["gender"] == "female"]
    mal = [v for v in pool if v["gender"] == "male"]
    narr = [v for v in fem if any(k in (v.get("use_case") or "") for k in ("narrat", "informative", "conversational"))]
    prompter = (narr or fem or mal or [None])[0]
    fem = [v for v in fem if v is not prompter][:per_gender]
    mal = mal[:per_gender]

    async def entry(v):
        return {"id": await add_shared(v), "source_id": v["voice_id"], "name": v["name"], "gender": v["gender"],
                "accent": v.get("accent") or "", "locale": v.get("locale") or "", "description": (v.get("description") or "")[:200],
                "preview_url": v.get("preview_url"), "owned": True}

    voices = [await entry(v) for v in [x for pair in zip(fem, mal) for x in pair] + fem[len(mal):] + mal[len(fem):]]
    log.info("catálogo pt-PT: %s", [(v["name"], v["gender"], v["id"]) for v in voices])
    return {"voices": voices, "prompter": await entry(prompter) if prompter else None, "model": TTS_MODEL, "source": "api"}


# Public library voices tagged "Portuguese · European" (verified to synthesise with this key); used without Voices: Read.
SEED_VOICES = [
    ("bBNhdwrIjl4fcVYiRbT2", "Marta", "female", "quente, confiante"),
    ("RlGHmE2fztwdBDat0jYf", "Diogo", "male", "caloroso, conversacional"),
    ("IZipF5JhqPlWzpduTV0E", "Daniela", "female", "madura, autoritária"),
    ("pjqwOzrEUZ3n3m4rMWWL", "Vasco", "male", "sóbrio, natural"),
    ("NkpT2jezTenCDRKHkWiX", "Benedita", "female", "jovem, luminosa"),
    ("5tqq6ewvJtcNtaffrqUJ", "Duarte", "male", "simpático, descontraído"),
    ("zKjRewuiqTkXNUVAMwat", "Mariza", "female", "fria, calma"),
    ("RROBrqjHiRb8zmRgGV11", "Dinis", "male", "jovem, optimista"),
    ("aLFUti4k8YKvtQGXv0UO", "Paulo", "male", "sotaque de Lisboa"),
]
SEED_PROMPTER = ("nJ5NFqyKb8kn9JBPmo6i", "Joana", "female", "natural, suave")


def _seed(v) -> dict:
    vid, name, gender, desc = v
    return {"id": vid, "source_id": vid, "name": name, "gender": gender, "accent": "European Portuguese", "locale": "pt-PT",
            "description": desc, "preview_url": None, "owned": False}


def seed_catalog() -> dict:
    return {"voices": [_seed(v) for v in SEED_VOICES], "prompter": _seed(SEED_PROMPTER), "model": TTS_MODEL, "source": "seed"}


def set_key(key: str):
    global KEY
    KEY = (key or "").strip()
    old = _http.pop("c", None)
    if old:
        asyncio.ensure_future(old.aclose())
    STATUS.update(checked_at=0.0, valid=None, perms={}, errors={})


async def user_info() -> dict:
    r = await req("GET", "/v1/user")
    sub = r.json().get("subscription") or {}
    return {"character_count": sub.get("character_count"), "character_limit": sub.get("character_limit"), "tier": sub.get("tier")}
