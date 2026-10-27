import os
import re
import io
import json
import uuid
import hashlib
import asyncio
import logging
import tempfile
import difflib
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Annotated, Literal

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict  # noqa: E402
from bson import ObjectId  # noqa: E402
from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone  # noqa: E402
from emergentintegrations.llm.openai import OpenAITextToSpeech, OpenAISpeechToText  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ensaio")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVEN_MODEL = "eleven_flash_v2_5"
LLM_MODEL = ("anthropic", "claude-sonnet-5-5")
FAST_MODEL = ("anthropic", "claude-haiku-5-5")
TTS_CACHE = ROOT_DIR / "tts_cache"
TTS_CACHE.mkdir(exist_ok=True)

VOICES = ["onyx", "nova", "echo", "coral", "ash", "shimmer", "fable", "sage", "verse", "ballad", "alloy"]
PROMPTER_VOICE = "sage"

app = FastAPI()
api = APIRouter(prefix="/api")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise HTTPException(404, "Não encontrado")
    return ObjectId(v)


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    def to_mongo(self) -> dict:
        d = self.model_dump(exclude={"id"})
        if self.id:
            d["_id"] = ObjectId(self.id)
        return d

    @classmethod
    def from_mongo(cls, doc):
        return cls.model_validate(doc) if doc else None


class Line(BaseModel):
    idx: int
    character: Optional[str] = None
    text: str
    kind: str = "dialogue"


class Character(BaseModel):
    name: str
    voice: str
    style: str = ""
    el_voice_id: Optional[str] = None
    el_voice_name: str = ""


class MemoryNote(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    text: str
    created_at: str = Field(default_factory=now)


class Script(BaseDocument):
    title: str
    author: str = ""
    raw_text: str
    characters: List[Character] = []
    lines: List[Line] = []
    memory: List[MemoryNote] = []
    created_at: str = Field(default_factory=now)
    last_rehearsal: Optional[str] = None
    last_score: Optional[float] = None


class Turn(BaseModel):
    line_idx: int
    expected: str
    said: str
    mode: str = "voz"
    kind: str = "line"
    accuracy: Optional[float] = None
    severity: str = "none"
    interrupted: bool = False
    feedback: str = ""
    differences: List[dict] = []
    created_at: str = Field(default_factory=now)


class Session(BaseDocument):
    script_id: str
    character: str
    instructions: str = ""
    strictness: str = "grave"
    start_idx: int = 0
    turns: List[Turn] = []
    status: str = "active"
    summary: Optional[dict] = None
    created_at: str = Field(default_factory=now)
    finished_at: Optional[str] = None


# ---------- LLM helpers ----------
async def ask_llm(system: str, prompt: str, model=LLM_MODEL) -> str:
    chat = LlmChat(api_key=LLM_KEY, session_id=uuid.uuid4().hex, system_message=system).with_model(*model)
    out = []
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)


def parse_json(s: str):
    s = re.sub(r"```(?:json)?", "", s)
    starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
    if not starts:
        raise ValueError("sem JSON")
    start = min(starts)
    end = max(s.rfind("}"), s.rfind("]"))
    return json.loads(s[start:end + 1])


# ---------- Script parsing ----------
UP = "A-ZÁÉÍÓÚÂÊÔÃÕÇÀÜ"
RE_INLINE = re.compile(rf"^\s*([{UP}][\w{UP}à-ÿ .'\-]{{0,30}}?)\s*(\([^)]*\))?\s*[:—–]\s*(.+)$")
RE_ALONE = re.compile(rf"^\s*([{UP}][{UP}0-9 .'\-]{{0,38}}[{UP}0-9])\s*(\([^)]*\))?\s*[.:]?\s*$")


def heuristic_parse(text: str):
    raw = [r.rstrip() for r in text.replace("\r", "").split("\n")]
    alone_counts = {}
    for r in raw:
        m = RE_ALONE.match(r)
        if m:
            alone_counts[m.group(1).strip()] = alone_counts.get(m.group(1).strip(), 0) + 1
    speakers_alone = {k for k, v in alone_counts.items() if v >= 2}
    lines, cur, speaker = [], None, None

    def flush():
        nonlocal cur
        if cur and cur["text"].strip():
            lines.append(cur)
        cur = None

    for r in raw:
        s = r.strip()
        if not s:
            flush()
            speaker = None
            continue
        m_alone = RE_ALONE.match(s)
        if m_alone and m_alone.group(1).strip() in speakers_alone:
            flush()
            speaker = m_alone.group(1).strip()
            continue
        m = RE_INLINE.match(s)
        if m and len(m.group(1).split()) <= 4:
            flush()
            speaker = m.group(1).strip()
            paren = (m.group(2) + " ") if m.group(2) else ""
            cur = {"character": speaker, "text": paren + m.group(3).strip(), "kind": "dialogue"}
            continue
        if s.startswith("(") and s.endswith(")"):
            flush()
            lines.append({"character": None, "text": s, "kind": "direction"})
            continue
        if cur and cur["kind"] == "dialogue":
            cur["text"] += " " + s
        elif speaker:
            cur = {"character": speaker, "text": s, "kind": "dialogue"}
        else:
            flush()
            lines.append({"character": None, "text": s, "kind": "direction"})
    flush()
    total = sum(len(x["text"]) for x in lines) or 1
    dial = [x for x in lines if x["kind"] == "dialogue"]
    ratio = sum(len(x["text"]) for x in dial) / total
    chars = {x["character"].upper() for x in dial}
    confident = len(dial) >= 2 and ratio >= 0.6 and len(chars) >= 1
    for x in dial:
        x["character"] = x["character"].upper()
    return lines, confident


PARSE_SYSTEM = (
    "És um assistente que estrutura textos de teatro/cinema em português. Recebes um excerto e devolves "
    "APENAS JSON: uma lista de objectos {\"c\": nome da personagem em MAIÚSCULAS ou null, \"t\": texto exacto, "
    "\"k\": \"d\" para fala ou \"r\" para rubrica/indicação cénica/título}. Não alteres nem resumas o texto das falas. "
    "Se o texto for um monólogo sem nomes, atribui as falas a uma personagem com um nome adequado."
)


def chunk_text(text: str, size: int = 6000):
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if len(cur) + len(para) > size and cur:
            parts.append(cur)
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        parts.append(cur)
    return parts


async def llm_parse(text: str):
    async def one(chunk):
        res = parse_json(await ask_llm(PARSE_SYSTEM, chunk))
        return [{"character": (x.get("c") or None) and x["c"].strip().upper(), "text": x["t"].strip(),
                 "kind": "dialogue" if x.get("k") == "d" and x.get("c") else "direction"} for x in res if x.get("t")]

    results = await asyncio.gather(*[one(c) for c in chunk_text(text)])
    return [x for r in results for x in r]


async def build_structure(text: str):
    lines, confident = heuristic_parse(text)
    if not confident:
        try:
            lines = await llm_parse(text)
        except Exception as e:
            log.exception("LLM parse falhou: %s", e)
    lines = [Line(idx=i, **x) for i, x in enumerate(lines)]
    names = []
    for ln in lines:
        if ln.kind == "dialogue" and ln.character not in names:
            names.append(ln.character)
    chars = [Character(name=n, voice=VOICES[i % len(VOICES)]) for i, n in enumerate(names)]
    return lines, chars


# ---------- Text extraction ----------
def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs)
    if name.endswith(".txt") or name.endswith(".md"):
        return data.decode("utf-8", errors="ignore")
    raise HTTPException(400, "Formato não suportado. Usa PDF, Word (.docx) ou texto (.txt).")


# ---------- Request models ----------
class ScriptIn(BaseModel):
    title: str
    author: str = ""
    text: str


class ScriptUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    characters: Optional[List[Character]] = None


class MemoryIn(BaseModel):
    text: str


class TTSIn(BaseModel):
    text: str
    voice: str = PROMPTER_VOICE
    character: Optional[str] = None
    style: str = ""
    el_voice_id: Optional[str] = None


class SessionIn(BaseModel):
    script_id: str
    character: str
    instructions: str = ""
    strictness: Literal["grave", "rigor", "nunca"] = "grave"
    start_idx: int = 0


class TurnIn(BaseModel):
    line_idx: int
    said: str
    mode: str = "voz"


async def get_script(script_id: str) -> Script:
    s = Script.from_mongo(await db.scripts.find_one({"_id": oid(script_id)}))
    if not s:
        raise HTTPException(404, "Texto não encontrado")
    return s


async def get_session(session_id: str) -> Session:
    s = Session.from_mongo(await db.sessions.find_one({"_id": oid(session_id)}))
    if not s:
        raise HTTPException(404, "Ensaio não encontrado")
    return s


def memory_block(script: Script) -> str:
    if not script.memory:
        return "(sem notas)"
    return "\n".join(f"- {m.text}" for m in script.memory)


# ---------- Scripts ----------
@api.get("/")
async def root():
    return {"message": "Ensaio API"}


@api.post("/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    text = extract_text(file.filename or "", data).strip()
    if not text:
        raise HTTPException(400, "Não foi possível extrair texto do ficheiro.")
    return {"text": text, "filename": file.filename}


@api.get("/scripts")
async def list_scripts():
    docs = await db.scripts.find({}, {"raw_text": 0}).sort("created_at", -1).to_list(500)
    out = []
    for d in docs:
        d.setdefault("raw_text", "")
        s = Script.from_mongo(d).model_dump()
        s["line_count"] = len([x for x in s["lines"] if x["kind"] == "dialogue"])
        s.pop("lines")
        out.append(s)
    return out


@api.post("/scripts")
async def create_script(body: ScriptIn):
    if not body.text.strip():
        raise HTTPException(400, "O texto está vazio.")
    lines, chars = await build_structure(body.text)
    if not any(ln.kind == "dialogue" for ln in lines):
        raise HTTPException(422, "Não consegui identificar falas e personagens neste texto.")
    s = Script(title=body.title.strip() or "Sem título", author=body.author, raw_text=body.text, lines=lines, characters=chars)
    assign_default_eleven(s)
    res = await db.scripts.insert_one(s.to_mongo())
    s.id = str(res.inserted_id)
    return s.model_dump()


@api.get("/scripts/{script_id}")
async def read_script(script_id: str):
    return (await get_script(script_id)).model_dump()


@api.put("/scripts/{script_id}")
async def update_script(script_id: str, body: ScriptUpdate):
    await get_script(script_id)
    if body.characters and any(c.voice not in VOICES for c in body.characters):
        raise HTTPException(400, "Voz inválida")
    upd = body.model_dump(exclude_none=True)
    if upd:
        await db.scripts.update_one({"_id": oid(script_id)}, {"$set": upd})
    return (await get_script(script_id)).model_dump()


@api.delete("/scripts/{script_id}")
async def delete_script(script_id: str):
    await db.scripts.delete_one({"_id": oid(script_id)})
    await db.sessions.delete_many({"script_id": script_id})
    return {"ok": True}


@api.post("/scripts/{script_id}/memory")
async def add_memory(script_id: str, body: MemoryIn):
    if not body.text.strip():
        raise HTTPException(400, "A nota está vazia.")
    await get_script(script_id)
    note = MemoryNote(text=body.text.strip())
    await db.scripts.update_one({"_id": oid(script_id)}, {"$push": {"memory": note.model_dump()}})
    return note.model_dump()


@api.delete("/scripts/{script_id}/memory/{note_id}")
async def delete_memory(script_id: str, note_id: str):
    await db.scripts.update_one({"_id": oid(script_id)}, {"$pull": {"memory": {"id": note_id}}})
    return {"ok": True}


@api.get("/scripts/{script_id}/sessions")
async def script_sessions(script_id: str):
    docs = await db.sessions.find({"script_id": script_id}).sort("created_at", -1).to_list(200)
    return [Session.from_mongo(d).model_dump(exclude={"turns"}) for d in docs]


# ---------- Voice ----------
def clean_for_tts(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[*_#>~|\[\]]", "", text)
    return re.sub(r"\s+", " ", text).strip()


TTS_INFLIGHT: dict = {}
TTS_SEM = asyncio.Semaphore(6)


def tts_instructions(character: Optional[str], style: str) -> str:
    who = f"Estás a dar voz à personagem {character}." if character else "És o apontador de um ensaio: fala de forma calma, breve e clara."
    return (
        "Fala em português de Portugal (português europeu, nunca brasileiro). "
        f"{who} {style} Diz a fala de forma natural e conversacional, como uma pessoa real numa conversa, "
        "com ritmo e respiração naturais, sem exageros nem tom de locutor."
    )


async def _generate(text: str, voice: str, instructions: str) -> bytes:
    engine = OpenAITextToSpeech(api_key=LLM_KEY)
    async with TTS_SEM:
        for attempt in range(2):
            try:
                return await asyncio.wait_for(engine.generate_speech(
                    text=text, model="gpt-4o-mini-tts", voice=voice, instructions=instructions), timeout=9)
            except Exception as e:
                log.warning("gpt-4o-mini-tts tentativa %s falhou: %s", attempt, e)
        fallback = voice if voice not in ("ballad", "verse") else "alloy"
        return await asyncio.wait_for(engine.generate_speech(text=text, model="tts-1", voice=fallback), timeout=20)


async def _generate_eleven(text: str, voice_id: str) -> bytes:
    from elevenlabs import VoiceSettings
    from elevenlabs.client import AsyncElevenLabs
    client = AsyncElevenLabs(api_key=ELEVEN_KEY, timeout=20.0)
    async with TTS_SEM:
        out = b""
        async for chunk in client.text_to_speech.convert(
            voice_id=voice_id, text=text, model_id=ELEVEN_MODEL, language_code="pt", output_format="mp3_44100_64",
            voice_settings=VoiceSettings(stability=0.45, similarity_boost=0.8, style=0.2, use_speaker_boost=True),
        ):
            out += chunk
        return out


async def synth(text: str, voice: str, character: Optional[str] = None, style: str = "",
                el_voice_id: Optional[str] = None) -> bytes:
    text = clean_for_tts(text)[:4000]
    if not text:
        raise HTTPException(400, "Texto vazio")
    voice = voice if voice in VOICES else PROMPTER_VOICE
    if ELEVEN_KEY and not el_voice_id and not character:
        el_voice_id = PROMPTER_EL
    use_el = bool(ELEVEN_KEY and el_voice_id)
    instructions = tts_instructions(character, style)
    sig = f"{text}|el|{el_voice_id}|{ELEVEN_MODEL}" if use_el else f"{text}|{voice}|gpt-4o-mini-tts|mp3|{instructions}"
    key = hashlib.sha256(sig.encode()).hexdigest()
    path = TTS_CACHE / f"{key}.mp3"
    if path.exists():
        return path.read_bytes()
    if key not in TTS_INFLIGHT:
        async def job():
            try:
                audio = None
                if use_el:
                    try:
                        audio = await _generate_eleven(text, el_voice_id)
                    except Exception as e:
                        log.warning("ElevenLabs falhou (%s), a usar OpenAI", e)
                audio = audio or await _generate(text, voice, instructions)
                path.write_bytes(audio)
                return audio
            finally:
                TTS_INFLIGHT.pop(key, None)
        TTS_INFLIGHT[key] = asyncio.ensure_future(job())
    return await asyncio.shield(TTS_INFLIGHT[key])


async def prepare_audio(script: Script, character: str, start_idx: int):
    voices = {c.name: c for c in script.characters}
    todo = [ln for ln in script.lines[start_idx:] + script.lines[:start_idx]
            if ln.kind == "dialogue" and ln.character != character]
    await asyncio.gather(*[synth(ln.text, voices[ln.character].voice, ln.character, voices[ln.character].style,
                                 voices[ln.character].el_voice_id)
                           for ln in todo], return_exceptions=True)


ELEVEN_PREMADE = [
    ("JBFqnCBsd6RMkjVDRZzb", "George", "male"), ("EXAVITQu4vr4xnSDxMaL", "Sarah", "female"),
    ("onwK4e9ZLuTAKqWVaz9q", "Daniel", "male"), ("XrExE9yKIg1WjnnlVkGX", "Matilda", "female"),
    ("nPczCjzI2devNBz1zQrb", "Brian", "male"), ("FGY2WhTYpPnrIDTdsKH5", "Laura", "female"),
    ("cjVigY5qzO86Huf0OWal", "Eric", "male"), ("XB0fDUnXU5powFXDhCwa", "Charlotte", "female"),
    ("iP95p4xoKVk53GoZ742B", "Chris", "male"), ("cgSgspJ2msm6clMCkdW9", "Jessica", "female"),
    ("pqHfZKP75CvOlQylNhV4", "Bill", "male"), ("pFZP5JQG7iQjIQuC4Bku", "Lily", "female"),
    ("TX3LPaxmHKxFdv7VOQHJ", "Liam", "male"), ("Xb7hH8MSUJpSbSDYk0k2", "Alice", "female"),
    ("N2lVS1w4EtoT3dr4eOWO", "Callum", "male"), ("SAz9YHcvj6GT2YYXdXww", "River", "neutral"),
]
PROMPTER_EL = "EXAVITQu4vr4xnSDxMaL"


def premade_voices() -> list:
    return [{"id": i, "name": n, "gender": g, "accent": "multilingue", "owned": True, "premade": True}
            for i, n, g in ELEVEN_PREMADE]


def guess_female(name: str) -> bool:
    first = name.strip().split()[0].lower() if name.strip() else ""
    return first.endswith("a") or first in {"inês", "isabel", "raquel", "beatriz", "mãe", "avó", "rainha", "senhora", "dona"}


def assign_default_eleven(script: Script, voices: Optional[list] = None) -> bool:
    if not ELEVEN_KEY:
        return False
    pool = [v for v in (voices or premade_voices()) if v["id"] != PROMPTER_EL] or premade_voices()
    fem = [v for v in pool if v.get("gender") == "female"] or pool
    mal = [v for v in pool if v.get("gender") != "female"] or pool
    used, changed = {c.el_voice_id for c in script.characters if c.el_voice_id}, False
    for c in script.characters:
        if c.el_voice_id:
            continue
        group = fem if guess_female(c.name) else mal
        v = next((x for x in group if x["id"] not in used), group[len(used) % len(group)])
        c.el_voice_id, c.el_voice_name = v["id"], v["name"]
        used.add(v["id"])
        changed = True
    return changed


async def eleven_pt_voices() -> list:
    from elevenlabs.client import AsyncElevenLabs
    client = AsyncElevenLabs(api_key=ELEVEN_KEY, timeout=20.0)
    out, seen = [], set()
    try:
        mine = await client.voices.get_all()
    except Exception as e:
        log.warning("Sem permissão para listar vozes ElevenLabs (%s); a usar vozes pré-definidas", str(e)[-120:])
        return premade_voices()
    for v in mine.voices:
        labels = v.labels or {}
        out.append({"id": v.voice_id, "name": v.name, "gender": labels.get("gender", ""),
                    "accent": labels.get("accent", ""), "preview_url": v.preview_url, "owned": True})
        seen.add(v.voice_id)
    try:
        res = await client.voices.get_shared(language="pt", page_size=100)
    except Exception:
        return out + [v for v in premade_voices() if v["id"] not in seen]
    for v in res.voices:
        tag = f"{v.accent or ''} {v.locale or ''}".lower()
        if not any(k in tag for k in ("pt-pt", "europ", "portug", "lisbo")) or "braz" in tag or "pt-br" in tag:
            continue
        out.append({"id": v.voice_id, "name": v.name, "gender": v.gender or "", "accent": v.accent or "",
                    "preview_url": v.preview_url, "owned": False, "public_user_id": v.public_owner_id})
    return out


async def ensure_eleven_voice(v: dict) -> str:
    if v.get("owned"):
        return v["id"]
    from elevenlabs.client import AsyncElevenLabs
    client = AsyncElevenLabs(api_key=ELEVEN_KEY, timeout=20.0)
    try:
        r = await client.voices.share(v["public_user_id"], v["id"], new_name=f"Ensaio {v['name']}"[:40])
        return r.voice_id
    except Exception as e:
        log.warning("não consegui adicionar a voz partilhada (%s); a usar id directo", e)
        return v["id"]


@api.get("/voices")
async def list_voices():
    data = {"provider": "elevenlabs" if ELEVEN_KEY else "openai", "openai": VOICES, "elevenlabs": []}
    if ELEVEN_KEY:
        try:
            data["elevenlabs"] = await eleven_pt_voices()
        except Exception as e:
            log.exception("ElevenLabs voices: %s", e)
            data["error"] = "Não consegui obter as vozes ElevenLabs. Verifica a chave."
    return data


class ElevenVoiceIn(BaseModel):
    character: str
    voice: dict


@api.post("/scripts/{script_id}/eleven-voice")
async def set_eleven_voice(script_id: str, body: ElevenVoiceIn):
    if not ELEVEN_KEY:
        raise HTTPException(400, "ElevenLabs não está configurado.")
    script = await get_script(script_id)
    vid = await ensure_eleven_voice(body.voice)
    for c in script.characters:
        if c.name == body.character:
            c.el_voice_id, c.el_voice_name = vid, body.voice.get("name", "")
    await db.scripts.update_one({"_id": oid(script_id)}, {"$set": {"characters": [c.model_dump() for c in script.characters]}})
    return script.model_dump()


@api.post("/scripts/{script_id}/auto-voices")
async def auto_eleven_voices(script_id: str):
    if not ELEVEN_KEY:
        raise HTTPException(400, "ElevenLabs não está configurado.")
    script = await get_script(script_id)
    voices = await eleven_pt_voices()
    if not voices:
        raise HTTPException(404, "Não encontrei vozes ElevenLabs em português de Portugal.")
    for c in script.characters:
        c.el_voice_id = None
    assign_default_eleven(script, voices)
    for c in script.characters:
        v = next(x for x in voices if x["id"] == c.el_voice_id)
        c.el_voice_id = await ensure_eleven_voice(v)
    await db.scripts.update_one({"_id": oid(script_id)}, {"$set": {"characters": [c.model_dump() for c in script.characters]}})
    return script.model_dump()


@api.post("/tts")
async def tts(body: TTSIn):
    audio = await synth(body.text, body.voice, body.character, body.style, body.el_voice_id)
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})


async def transcribe(data: bytes, ext: str, hint: str = "") -> str:
    if len(data) < 1000:
        return ""
    if ext not in OpenAISpeechToText.FILE_FORMATS:
        ext = "webm"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    prompt = "Transcrição literal em português de Portugal, com as palavras tal como são ditas, incluindo formas coloquiais."
    if hint:
        prompt = f"{prompt} {clean_for_tts(hint)[:600]}"
    try:
        engine = OpenAISpeechToText(api_key=LLM_KEY)
        with open(tmp_path, "rb") as f:
            res = await engine.transcribe(file=f, model="whisper-1", language="pt", prompt=prompt, temperature=0)
    finally:
        os.unlink(tmp_path)
    text = getattr(res, "text", None) or (res.get("text") if isinstance(res, dict) else str(res))
    return (text or "").strip()


@api.post("/stt")
async def stt(file: UploadFile = File(...)):
    data = await file.read()
    return {"text": await transcribe(data, (file.filename or "a.webm").rsplit(".", 1)[-1].lower())}


# ---------- Local fast matching ----------
NUMS = {"0": "zero", "1": "um", "2": "dois", "3": "tres", "4": "quatro", "5": "cinco", "6": "seis", "7": "sete",
        "8": "oito", "9": "nove", "10": "dez", "11": "onze", "12": "doze", "15": "quinze", "20": "vinte",
        "30": "trinta", "100": "cem"}
COLLOQUIAL = [
    (r"\bpara (a|à)\b", "pra"), (r"\bpara o\b", "pro"), (r"\b(para|pa|pra)\b", "pra"),
    (r"\bestas\b", "tas"), (r"\besta\b", "ta"), (r"\bestou\b", "tou"), (r"\bestava\b", "tava"),
    (r"\bestavas\b", "tavas"), (r"\bestamos\b", "tamos"), (r"\bestao\b", "tao"),
    (r"\bnao e\b", "ne"), (r"\bcom o\b", "co"), (r"\bcom a\b", "ca"), (r"\bde um\b", "dum"), (r"\bde uma\b", "duma"),
    (r"\bem um\b", "num"), (r"\bem uma\b", "numa"), (r"\bpois e\b", "poise"),
]
FILLERS = {"hum", "hmm", "eh", "ah", "ahn", "uh", "um hum", "pronto"}


def norm_tokens(text: str) -> List[str]:
    t = re.sub(r"\([^)]*\)", " ", text.lower())
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[-'’`´]", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = " ".join(NUMS.get(w, w) for w in t.split())
    for pat, rep in COLLOQUIAL:
        t = re.sub(pat, rep, t)
    return [w for w in t.split() if w not in FILLERS]


def local_match(expected: str, said: str, fuzzy_ratio: float = 0.75) -> dict:
    exp, got = norm_tokens(expected), norm_tokens(said)
    if not exp:
        return {"accuracy": 100.0, "max_gap": 0, "extra": 0, "differences": []}
    sm = difflib.SequenceMatcher(a=exp, b=got, autojunk=False)
    matched, extra, max_gap, diffs = 0, 0, 0, []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        a, b = exp[i1:i2], got[j1:j2]
        if op == "equal":
            matched += len(a)
            continue
        if op == "replace":
            fuzzy = sum(1 for x, y in zip(a, b) if difflib.SequenceMatcher(a=x, b=y).ratio() >= fuzzy_ratio)
            matched += fuzzy
            if fuzzy == len(a) == len(b):
                continue
            max_gap = max(max_gap, len(a) - fuzzy)
            extra += max(0, len(b) - len(a))
            diffs.append({"expected": " ".join(a), "said": " ".join(b), "type": "troca"})
        elif op == "delete":
            max_gap = max(max_gap, len(a))
            diffs.append({"expected": " ".join(a), "said": "", "type": "omissão" if len(a) < 5 else "salto"})
        elif op == "insert":
            extra += len(b)
            diffs.append({"expected": "", "said": " ".join(b), "type": "acrescento"})
    return {"accuracy": round(100 * matched / len(exp), 1), "max_gap": max_gap, "extra": extra, "differences": diffs}


NEGATIONS = {"nao", "ne", "nunca", "nada", "nem", "ninguem", "jamais", "sim"}
NEEDS_AI = re.compile(r"\b(texto|linha|deixa|mudamos|mudaram|agora digo|passei a dizer|em vez de|cortamos|nao me lembro|como e que e)\b")


def fast_verdict(strictness: str, m: dict, n_words: int, said: str = ""):
    """Devolve (aceita_já, severidade) ou None para pedir à IA."""
    acc, gap, extra = m["accuracy"], m["max_gap"], m["extra"]
    if acc < 97 and NEEDS_AI.search(" ".join(norm_tokens(said))):
        return None
    if strictness == "nunca":
        return (True, ("none" if acc >= 97 else "minor")) if acc >= 50 else None
    if any(w in NEGATIONS for d in m["differences"] for w in f"{d['expected']} {d['said']}".split()):
        return None
    if strictness == "rigor":
        if acc >= 97 and extra <= 1:
            return True, "none"
        return None
    short = n_words <= 3
    if acc >= 97 and extra <= 2:
        return True, "none"
    if (acc >= (50 if short else 72)) and gap < 5 and extra < max(4, n_words // 2):
        return True, "minor"
    return None


# ---------- Sessions ----------
@api.post("/sessions")
async def create_session(body: SessionIn):
    script = await get_script(body.script_id)
    if body.character not in [c.name for c in script.characters]:
        raise HTTPException(400, "Personagem inválida")
    if assign_default_eleven(script):
        await db.scripts.update_one({"_id": oid(script.id)}, {"$set": {"characters": [c.model_dump() for c in script.characters]}})
    s = Session(**body.model_dump())
    res = await db.sessions.insert_one(s.to_mongo())
    s.id = str(res.inserted_id)
    asyncio.create_task(prepare_audio(script, body.character, body.start_idx))
    return s.model_dump()


@api.get("/sessions/{session_id}")
async def read_session(session_id: str):
    return (await get_session(session_id)).model_dump()


TURN_SYSTEM = """És o apontador de um actor num ensaio. PT-PT. Sê rápido e breve.
Recebes: fala esperada, o que o actor disse (transcrição automática de voz ou texto escrito), instruções do actor, memória do texto (alterações acordadas que SUBSTITUEM o original) e as diferenças já detectadas automaticamente.

ATENÇÃO à transcrição automática: normaliza a fala, por isso formas coloquiais ou contraídas (prá/pra/para, tá/está, tou/estou, pró/para o, né/não é, cum/com, etc.), elisões, sotaque e pequenas palavras mal ouvidas NÃO são erros. Se a diferença pode ser explicada por pronúncia ou reconhecimento, considera que o actor disse bem.

Classifica:
- "line": tentou dizer a fala (em caso de dúvida, é "line").
- "note": informação para memorizar sobre o texto (ex.: "aí mudámos nos ensaios, agora digo X em vez de Y").
- "help": pede a deixa ("texto!", "linha", "não me lembro").
- "other": comentário claramente dirigido a ti.

Interrupção (só para "line"): segue as instruções do actor. Mesmo no modo rigoroso, interrompe apenas por palavras realmente trocadas, omitidas ou acrescentadas que mudam o texto — nunca por pronúncia, contracções, pontuação, ordem equivalente de interjeições ou possíveis erros de transcrição. Sem instruções: só erros graves (saltos grandes, sentido alterado).

Responde APENAS JSON compacto:
{"kind":"line|note|help|other","accuracy":0-100,"severity":"none|minor|major","interrupt":true|false,"feedback":"uma frase curta falada em PT-PT (se interromperes: o que falhou e o trecho correcto; se note: confirma; se help: as primeiras palavras da fala); vazio se seguir","differences":[{"expected":"","said":"","type":"omissão|troca|acrescento|repetição|salto|inversão"}],"memory_note":"para note: a nota autónoma citando a fala; senão vazio"}"""


async def evaluate_turn(session: Session, script: Script, line_idx: int, said: str, mode: str) -> dict:
    if line_idx < 0 or line_idx >= len(script.lines):
        raise HTTPException(400, "Fala inválida")
    line = script.lines[line_idx]
    m = local_match(line.text, said, 0.9 if session.strictness == "rigor" else 0.75)
    exp_tokens = norm_tokens(line.text)
    notes = [" ".join(norm_tokens(n.text)) for n in script.memory]
    in_memory = any(" ".join(exp_tokens[i:i + 4]) in n for n in notes for i in range(max(1, len(exp_tokens) - 3)))
    verdict = None if in_memory else fast_verdict(session.strictness, m, len(exp_tokens), said)
    note = None
    if verdict:
        _, severity = verdict
        turn = Turn(line_idx=line_idx, expected=line.text, said=said, mode=mode, kind="line",
                    accuracy=m["accuracy"], severity=severity, differences=m["differences"])
    else:
        prev = next((ln for ln in reversed(script.lines[:line_idx]) if ln.kind == "dialogue"), None)
        prompt = (
            f"Instruções do actor: {session.instructions or '(nenhuma)'}\n"
            f"Memória do texto:\n{memory_block(script)}\n"
            f"Deixa anterior ({prev.character if prev else '-'}): {prev.text if prev else '-'}\n"
            f"Fala esperada ({line.character}): {line.text}\n"
            f"O actor disse ({mode}): {said}\n"
            f"Diferenças automáticas (precisão {m['accuracy']}%): {json.dumps(m['differences'], ensure_ascii=False)}"
        )
        try:
            r = parse_json(await ask_llm(TURN_SYSTEM, prompt, FAST_MODEL))
        except Exception as e:
            log.exception("avaliação falhou: %s", e)
            r = {"kind": "line", "accuracy": m["accuracy"], "severity": "major", "interrupt": False}
        kind = r.get("kind", "line")
        turn = Turn(
            line_idx=line_idx, expected=line.text, said=said, mode=mode, kind=kind,
            accuracy=r.get("accuracy", m["accuracy"]) if kind == "line" else None, severity=r.get("severity", "none"),
            interrupted=bool(r.get("interrupt")) and kind == "line" and session.strictness != "nunca",
            feedback=r.get("feedback", "") or "",
            differences=r.get("differences", []) if kind == "line" else [],
        )
        if kind == "note" and r.get("memory_note"):
            note = MemoryNote(text=r["memory_note"])
            await db.scripts.update_one({"_id": oid(script.id)}, {"$push": {"memory": note.model_dump()}})
            if not turn.feedback:
                turn.feedback = "Anotado. Vou ter isso em conta."
    await db.sessions.update_one({"_id": oid(session.id)}, {"$push": {"turns": turn.model_dump()}})
    return {
        "turn": turn.model_dump(),
        "advance": turn.kind == "line" and not turn.interrupted,
        "memory_note": note.model_dump() if note else None,
    }


@api.post("/sessions/{session_id}/turn")
async def session_turn(session_id: str, body: TurnIn):
    session = await get_session(session_id)
    script = await get_script(session.script_id)
    return await evaluate_turn(session, script, body.line_idx, body.said, body.mode)


@api.post("/sessions/{session_id}/voice-turn")
async def session_voice_turn(session_id: str, line_idx: int = Form(...), file: UploadFile = File(...)):
    session = await get_session(session_id)
    script = await get_script(session.script_id)
    if line_idx < 0 or line_idx >= len(script.lines):
        raise HTTPException(400, "Fala inválida")
    data = await file.read()
    said = await transcribe(data, (file.filename or "a.webm").rsplit(".", 1)[-1].lower(), script.lines[line_idx].text)
    if not said:
        return {"said": "", "turn": None, "advance": False, "memory_note": None}
    res = await evaluate_turn(session, script, line_idx, said, "voz")
    return {"said": said, **res}


SUMMARY_SYSTEM = """És um treinador de texto experiente para actores. Falas português de Portugal (PT-PT).
Recebes as falas que o actor ensaiou (texto esperado vs. o que disse, em cada tentativa), as instruções e a memória do texto (alterações acordadas que substituem o original).
Faz um resumo detalhado da prestação. É OBRIGATÓRIO listar TUDO o que foi diferente do texto fornecido (cada omissão, troca, acrescento, repetição, salto), mesmo pequenas coisas, ignorando apenas pontuação, erros evidentes de transcrição automática e formas coloquiais/contraídas equivalentes (prá/para, tá/está, tou/estou, etc.), que a transcrição normaliza e NÃO são erros.
Sugere zonas a rever e dá técnicas de memorização concretas e adaptadas aos erros observados (ex.: ligar a fala à deixa, imagens mentais, palavras-âncora, ritmo).
Responde APENAS com JSON:
{"score":0-100,"overview":"parágrafo de síntese","strengths":["..."],
 "differences":[{"line_idx":n,"expected":"trecho","said":"trecho","type":"omissão|troca|acrescento|repetição|salto|inversão","note":"comentário curto"}],
 "zones_to_review":[{"line_idx":n,"reason":"..."}],
 "memorization_tips":["..."],
 "next_steps":"o que fazer no próximo ensaio"}"""


@api.post("/sessions/{session_id}/finish")
async def finish_session(session_id: str):
    session = await get_session(session_id)
    if session.status == "finished" and session.summary:
        return session.model_dump()
    script = await get_script(session.script_id)
    line_turns = [t for t in session.turns if t.kind == "line"]
    attempted = sorted({t.line_idx for t in line_turns})
    stats = {
        "lines_attempted": len(attempted),
        "attempts": len(line_turns),
        "interruptions": sum(1 for t in line_turns if t.interrupted),
        "avg_accuracy": round(sum(t.accuracy or 0 for t in line_turns) / len(line_turns), 1) if line_turns else None,
    }
    if not line_turns:
        summary = {"score": None, "overview": "Não houve falas ditas neste ensaio.", "strengths": [], "differences": [],
                   "zones_to_review": [], "memorization_tips": [], "next_steps": ""}
    else:
        detail = "\n\n".join(
            f"[fala {t.line_idx}] ESPERADO: {t.expected}\nDISSE ({t.mode}): {t.said}\n"
            f"avaliação imediata: precisão {t.accuracy}, {'interrompido' if t.interrupted else 'seguiu'}"
            for t in line_turns
        )
        prompt = (f"Texto: {script.title}\nPersonagem: {session.character}\nInstruções: {session.instructions or '(nenhuma)'}\n"
                  f"Memória do texto:\n{memory_block(script)}\n\nTentativas:\n{detail}")
        try:
            summary = parse_json(await ask_llm(SUMMARY_SYSTEM, prompt))
        except Exception as e:
            log.exception("resumo falhou: %s", e)
            raise HTTPException(502, "Não consegui gerar o resumo. Tenta outra vez.")
    summary["stats"] = stats
    fin = now()
    await db.sessions.update_one({"_id": oid(session_id)}, {"$set": {"status": "finished", "summary": summary, "finished_at": fin}})
    await db.scripts.update_one({"_id": oid(script.id)}, {"$set": {"last_rehearsal": fin, "last_score": summary.get("score")}})
    return (await get_session(session_id)).model_dump()


DEMO_TEXT = """Cena única. Uma estação de comboios, ao fim da tarde.

(MARTA está sentada num banco. Entra JOÃO, com uma mala.)

JOÃO: Ainda estás aqui? Pensei que já tivesses partido no comboio das seis.
MARTA: Perdi-o. Ou melhor, deixei-o ir. Fiquei a vê-lo afastar-se e não me mexi.
JOÃO: Porquê?
MARTA: Porque não sabia se queria mesmo ir. Há dias em que partir parece a coisa mais fácil do mundo, e há outros em que pesa como uma pedra.
JOÃO: E hoje é dia de pedra.
MARTA: Hoje é dia de pedra.

(Pausa. JOÃO pousa a mala e senta-se ao lado dela.)

JOÃO: Sabes o que dizia a minha avó? Que as estações são os únicos sítios onde toda a gente está à espera de alguma coisa, e ninguém tem vergonha de o admitir.
MARTA: A tua avó era uma mulher sábia.
JOÃO: Era teimosa. Mas também era sábia. Uma coisa não impede a outra.
CHEFE DA ESTAÇÃO: O último comboio para Coimbra parte dentro de dez minutos, linha dois!
MARTA: Ouviste? Dez minutos.
JOÃO: Ouvi. E então? Vais ou ficas?
MARTA: Vou. Mas só se me prometeres que, quando eu voltar, ainda cá estás.
JOÃO: Prometo. Afinal, alguém tem de ficar à espera."""


@app.on_event("startup")
async def seed():
    if await db.scripts.count_documents({}) == 0:
        lines, chars = await build_structure(DEMO_TEXT)
        s = Script(title="A Espera", author="Cena de demonstração", raw_text=DEMO_TEXT, lines=lines, characters=chars)
        assign_default_eleven(s)
        await db.scripts.insert_one(s.to_mongo())


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
