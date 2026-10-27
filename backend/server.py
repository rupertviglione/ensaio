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
import time
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
import eleven  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ensaio")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
LLM_MODEL = ("anthropic", "claude-sonnet-5-5")
FAST_MODEL = ("anthropic", "claude-haiku-5-5")
TTS_CACHE = ROOT_DIR / "tts_cache"
TTS_CACHE.mkdir(exist_ok=True)

VOICES = ["onyx", "nova", "echo", "coral", "ash", "shimmer", "fable", "sage", "verse", "ballad", "alloy"]
PROMPTER_VOICE = "sage"

app = FastAPI(title="Ensaio API", openapi_url="/api/openapi.json", docs_url="/api/docs", redoc_url=None)
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


def short_id() -> str:
    return uuid.uuid4().hex[:10]


class Line(BaseModel):
    uid: str = Field(default_factory=short_id)
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
    line_uid: Optional[str] = None
    new_text: Optional[str] = None
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
    focus_idxs: List[int] = []
    hint_seconds: int = 5
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
    line_idx: Optional[int] = None
    new_text: Optional[str] = None


class LineIn(BaseModel):
    uid: Optional[str] = None
    character: Optional[str] = None
    text: str
    kind: Literal["dialogue", "direction"] = "dialogue"


class LinesIn(BaseModel):
    lines: List[LineIn]


class RenameIn(BaseModel):
    old: str
    new: str


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
    focus_idxs: List[int] = []
    hint_seconds: int = Field(5, ge=3, le=15)


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


def edits_map(script: Script) -> dict:
    return {m.line_uid: m for m in script.memory if m.line_uid and m.new_text}


def effective_text(script: Script, ln: Line) -> str:
    m = edits_map(script).get(ln.uid)
    return m.new_text if m else ln.text


def script_out(script: Script) -> dict:
    d = script.model_dump()
    em = edits_map(script)
    for ln in d["lines"]:
        m = em.get(ln["uid"])
        ln["edited_text"] = m.new_text if m else None
        ln["edit_note_id"] = m.id if m else None
    return d


async def save_characters(script: Script):
    await db.scripts.update_one({"_id": oid(script.id)}, {"$set": {"characters": [c.model_dump() for c in script.characters]}})


LINK_SYSTEM = """Recebes as falas numeradas de um texto de teatro e uma nota de ensaio (alteração acordada). PT-PT.
Identifica a fala a que a nota se refere e escreve o texto completo da fala JÁ com a alteração aplicada (mantém tudo o resto exactamente igual).
Se a nota não for uma alteração concreta ao texto de uma fala, devolve line_idx null.
Responde APENAS JSON: {"line_idx": n|null, "new_text": "..."}"""


async def link_note(script: Script, note_text: str, hint_idx: Optional[int] = None) -> tuple:
    lines = "\n".join(f"[{ln.idx}] {ln.character}: {effective_text(script, ln)}" for ln in script.lines if ln.kind == "dialogue")
    hint = f"\nA nota foi dita durante a fala [{hint_idx}] (ou perto dela)." if hint_idx is not None else ""
    try:
        r = parse_json(await ask_llm(LINK_SYSTEM, f"Falas:\n{lines}{hint}\n\nNota: {note_text}", FAST_MODEL))
        idx = r.get("line_idx")
        if isinstance(idx, int) and 0 <= idx < len(script.lines) and r.get("new_text"):
            return script.lines[idx].uid, r["new_text"].strip()
    except Exception as e:
        log.warning("link_note falhou: %s", e)
    return None, None


async def link_note_bg(script: Script, note: MemoryNote, hint_idx: Optional[int]):
    uid, new_text = await link_note(script, note.text, hint_idx)
    if uid:
        await db.scripts.update_one({"_id": oid(script.id), "memory.id": note.id},
                                    {"$set": {"memory.$.line_uid": uid, "memory.$.new_text": new_text}})


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
    return script_out(s)


@api.get("/scripts/{script_id}")
async def read_script(script_id: str):
    return script_out(await get_script(script_id))


@api.put("/scripts/{script_id}/lines")
async def update_lines(script_id: str, body: LinesIn):
    script = await get_script(script_id)
    lines = []
    for x in body.lines:
        text = x.text.strip()
        if not text:
            continue
        char = (x.character or "").strip().upper() or None
        kind = x.kind if char or x.kind == "direction" else "direction"
        lines.append(Line(uid=x.uid or short_id(), idx=len(lines), character=char if kind == "dialogue" else None, text=text, kind=kind))
    if not any(ln.kind == "dialogue" for ln in lines):
        raise HTTPException(400, "O texto tem de ter pelo menos uma fala.")
    existing = {c.name: c for c in script.characters}
    names = []
    for ln in lines:
        if ln.kind == "dialogue" and ln.character not in names:
            names.append(ln.character)
    used = {c.voice for c in script.characters}
    free = [v for v in VOICES if v not in used] or VOICES
    chars = []
    for i, n in enumerate(names):
        chars.append(existing.get(n) or Character(name=n, voice=free[i % len(free)]))
    script.lines, script.characters = lines, chars
    assign_default_eleven(script)
    uids = {ln.uid for ln in lines}
    script.memory = [m for m in script.memory if not m.line_uid or m.line_uid in uids]
    await db.scripts.update_one({"_id": oid(script_id)}, {"$set": {
        "lines": [ln.model_dump() for ln in lines], "characters": [c.model_dump() for c in chars],
        "memory": [m.model_dump() for m in script.memory]}})
    return script_out(script)


@api.post("/scripts/{script_id}/rename-character")
async def rename_character(script_id: str, body: RenameIn):
    script = await get_script(script_id)
    new = body.new.strip().upper()
    if not new or body.old not in [c.name for c in script.characters]:
        raise HTTPException(400, "Nome inválido")
    if new == body.old:
        return script_out(script)
    for ln in script.lines:
        if ln.character == body.old:
            ln.character = new
    if new in [c.name for c in script.characters]:
        script.characters = [c for c in script.characters if c.name != body.old]
    else:
        for c in script.characters:
            if c.name == body.old:
                c.name = new
    await db.scripts.update_one({"_id": oid(script_id)}, {"$set": {
        "lines": [ln.model_dump() for ln in script.lines], "characters": [c.model_dump() for c in script.characters]}})
    return script_out(script)


@api.put("/scripts/{script_id}")
async def update_script(script_id: str, body: ScriptUpdate):
    await get_script(script_id)
    if body.characters and any(c.voice not in VOICES for c in body.characters):
        raise HTTPException(400, "Voz inválida")
    upd = body.model_dump(exclude_none=True)
    if upd:
        await db.scripts.update_one({"_id": oid(script_id)}, {"$set": upd})
    return script_out(await get_script(script_id))


@api.delete("/scripts/{script_id}")
async def delete_script(script_id: str):
    await db.scripts.delete_one({"_id": oid(script_id)})
    await db.sessions.delete_many({"script_id": script_id})
    return {"ok": True}


@api.post("/scripts/{script_id}/memory")
async def add_memory(script_id: str, body: MemoryIn):
    if not body.text.strip():
        raise HTTPException(400, "A nota está vazia.")
    script = await get_script(script_id)
    note = MemoryNote(text=body.text.strip())
    if body.line_idx is not None and body.new_text and 0 <= body.line_idx < len(script.lines):
        note.line_uid, note.new_text = script.lines[body.line_idx].uid, body.new_text.strip()
    else:
        note.line_uid, note.new_text = await link_note(script, note.text, body.line_idx)
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
CATALOG: dict = {"voices": [], "prompter": None}
PREMADE_IDS = {
    "JBFqnCBsd6RMkjVDRZzb", "EXAVITQu4vr4xnSDxMaL", "XrExE9yKIg1WjnnlVkGX", "nPczCjzI2devNBz1zQrb", "FGY2WhTYpPnrIDTdsKH5",
    "cjVigY5qzO86Huf0OWal", "XB0fDUnXU5powFXDhCwa", "iP95p4xoKVk53GoZ742B", "cgSgspJ2msm6clMCkdW9", "pqHfZKP75CvOlQylNhV4",
    "pFZP5JQG7iQjIQuC4Bku", "TX3LPaxmHKxFdv7VOQHJ", "Xb7hH8MSUJpSbSDYk0k2", "N2lVS1w4EtoT3dr4eOWO", "SAz9YHcvj6GT2YYXdXww",
    "onwK4e9ZLuTAKqWVaz9q",
}


def tts_instructions(character: Optional[str], style: str) -> str:
    who = f"Estás a dar voz à personagem {character}." if character else "És o apontador de um ensaio: fala de forma calma, breve e clara."
    return (
        "Fala em português de Portugal (português europeu, nunca brasileiro). "
        f"{who} {style} Diz a fala de forma natural e conversacional, como uma pessoa real numa conversa, "
        "com ritmo e respiração naturais, sem exageros nem tom de locutor."
    )


def hint_text(text: str) -> str:
    return " ".join(clean_for_tts(text).split()[:3])


async def _generate_openai(text: str, voice: str, instructions: str) -> bytes:
    engine = OpenAITextToSpeech(api_key=LLM_KEY)

    async def one(part: str) -> bytes:
        for attempt in range(2):
            try:
                return await asyncio.wait_for(engine.generate_speech(
                    text=part, model="gpt-4o-mini-tts", voice=voice, instructions=instructions), timeout=45)
            except Exception as e:
                if attempt:
                    raise
                log.warning("gpt-4o-mini-tts falhou (%s), nova tentativa", e)

    return b"".join(await asyncio.gather(*[one(p) for p in eleven.split_text(text, 1500)]))


def prompter_voice_id() -> Optional[str]:
    return (CATALOG.get("prompter") or {}).get("id")


def _fallback_reason(vid: Optional[str]) -> str:
    if not eleven.KEY:
        return "sem chave ElevenLabs"
    if not vid:
        return "personagem sem voz ElevenLabs"
    return "chave ElevenLabs sem permissão TTS" if not eleven.can("tts") else ""


async def synth(text: str, voice: str, character: Optional[str] = None, style: str = "",
                el_voice_id: Optional[str] = None) -> tuple:
    text = clean_for_tts(text)
    if not text:
        raise HTTPException(400, "Texto vazio")
    voice = voice if voice in VOICES else PROMPTER_VOICE
    el_voice_id = None if el_voice_id in PREMADE_IDS else el_voice_id
    vid = el_voice_id or (prompter_voice_id() if character is None else None)
    instructions = tts_instructions(character, style)
    el_key = hashlib.sha256(f"{text}|el|{vid}|{eleven.TTS_MODEL}".encode()).hexdigest()
    oa_key = hashlib.sha256(f"{text}|{voice}|gpt-4o-mini-tts|mp3|{instructions}".encode()).hexdigest()
    el_path, oa_path = TTS_CACHE / f"el_{el_key}.mp3", TTS_CACHE / f"oa_{oa_key}.mp3"
    use_el = bool(vid) and eleven.can("tts")
    if use_el and el_path.exists():
        return el_path.read_bytes(), "elevenlabs", vid
    if not use_el and oa_path.exists():
        return oa_path.read_bytes(), "openai", voice
    key = el_key if use_el else oa_key
    if key not in TTS_INFLIGHT:
        async def job():
            try:
                reason = _fallback_reason(vid)
                if use_el:
                    for attempt in range(2):
                        try:
                            audio = await eleven.synth(text, vid)
                            el_path.write_bytes(audio)
                            eleven.STATS["elevenlabs"] += 1
                            return audio, "elevenlabs", vid
                        except Exception as e:
                            reason = str(e)[:200]
                            log.warning("ElevenLabs TTS tentativa %s falhou: %s", attempt + 1, reason)
                            if isinstance(e, eleven.ElevenError) and e.status < 500:
                                break
                log.warning("TTS FALLBACK OpenAI (%s) voz=%s texto=%r", reason, voice, text[:60])
                eleven.STATS["openai_fallback"] += 1
                eleven.STATS["fallback_reasons"] = (eleven.STATS["fallback_reasons"] + [reason])[-20:]
                if oa_path.exists():
                    return oa_path.read_bytes(), "openai", voice
                async with TTS_SEM:
                    audio = await _generate_openai(text, voice, instructions)
                oa_path.write_bytes(audio)
                return audio, "openai", voice
            finally:
                TTS_INFLIGHT.pop(key, None)
        TTS_INFLIGHT[key] = asyncio.ensure_future(job())
    return await asyncio.shield(TTS_INFLIGHT[key])


async def prepare_audio(script: Script, character: str, start_idx: int):
    voices = {c.name: c for c in script.characters}
    order = script.lines[start_idx:] + script.lines[:start_idx]
    ai = [ln for ln in order if ln.kind == "dialogue" and ln.character != character and ln.character in voices]
    t0 = time.perf_counter()
    res = await asyncio.gather(*[synth(effective_text(script, ln), voices[ln.character].voice, ln.character,
                                       voices[ln.character].style, voices[ln.character].el_voice_id) for ln in ai],
                               return_exceptions=True)
    hints = {hint_text(effective_text(script, ln)) for ln in order if ln.kind == "dialogue" and ln.character == character}
    await asyncio.gather(*[synth(h, PROMPTER_VOICE) for h in hints if h], return_exceptions=True)
    fails = [r for r in res if isinstance(r, Exception)]
    log.info("pré-geração: %s falas IA (%s falhas, %s ElevenLabs) + %s dicas em %.1fs", len(ai), len(fails),
             sum(1 for r in res if isinstance(r, tuple) and r[1] == "elevenlabs"), len(hints), time.perf_counter() - t0)


def guess_female(name: str) -> bool:
    first = name.strip().split()[0].lower() if name.strip() else ""
    return first.endswith("a") or first in {"inês", "isabel", "raquel", "beatriz", "mãe", "avó", "rainha", "senhora", "dona", "mulher"}


def assign_default_eleven(script: Script) -> bool:
    pool = CATALOG["voices"]
    if not pool:
        return False
    fem = [v for v in pool if v["gender"] == "female"]
    mal = [v for v in pool if v["gender"] != "female"]
    used, changed = {c.el_voice_id for c in script.characters if c.el_voice_id and c.el_voice_id not in PREMADE_IDS}, False
    for c in script.characters:
        if c.el_voice_id and c.el_voice_id not in PREMADE_IDS:
            continue
        group = (fem if guess_female(c.name) else mal) or pool
        other = mal if group is fem else fem
        v = next((x for x in group + other if x["id"] not in used), group[len(used) % len(group)])
        c.el_voice_id, c.el_voice_name = v["id"], v["name"]
        used.add(v["id"])
        changed = True
    return changed


async def eleven_bootstrap(rebuild: bool = False):
    doc = await db.voice_catalog.find_one({"_id": "pt-PT"})
    if doc and doc.get("voices"):
        CATALOG.update(voices=doc["voices"], prompter=doc.get("prompter"), source=doc.get("source", "api"))
    st = await eleven.check_status(force=True)
    seeded = CATALOG.get("source") == "seed"
    if (rebuild or not CATALOG["voices"] or seeded) and (st["perms"].get("shared_voices") or (not CATALOG["voices"] and st["perms"].get("tts"))):
        try:
            cat = await eleven.build_catalog() if st["perms"].get("shared_voices") else eleven.seed_catalog()
            if cat["voices"] and not (seeded and cat["source"] == "seed"):
                CATALOG.update(voices=cat["voices"], prompter=cat["prompter"], source=cat["source"])
                await db.voice_catalog.update_one({"_id": "pt-PT"}, {"$set": {**cat, "updated_at": now()}}, upsert=True)
        except Exception as e:
            log.exception("catálogo pt-PT falhou: %s", e)
    n = 0
    async for d in db.scripts.find({}):
        s = Script.from_mongo(d)
        if assign_default_eleven(s):
            await save_characters(s)
            n += 1
    log.info("vozes: catálogo=%s, textos migrados=%s, avisos=%s", len(CATALOG["voices"]), n, eleven.messages())


def voices_info() -> dict:
    return {"provider": "elevenlabs" if CATALOG["voices"] and eleven.can("tts") else "openai", "openai": VOICES,
            "elevenlabs": CATALOG["voices"], "prompter": CATALOG["prompter"], "pt_native": bool(CATALOG["voices"]),
            "model": eleven.TTS_MODEL, "messages": eleven.messages()}


@api.get("/voices")
async def list_voices():
    await eleven.check_status()
    return voices_info()


@api.get("/eleven/status")
async def eleven_status(refresh: bool = False):
    if refresh:
        await eleven_bootstrap(rebuild=not CATALOG["voices"])
    st = await eleven.check_status()
    return {"configured": bool(eleven.KEY), "valid": st["valid"], "permissions": st["perms"], "errors": st["errors"],
            "messages": eleven.messages(), "tts_model": eleven.TTS_MODEL, "realtime_model": eleven.REALTIME_MODEL,
            "catalog": CATALOG["voices"], "prompter": CATALOG["prompter"], "stats": eleven.STATS}


@api.post("/stt/token")
async def stt_token():
    if not eleven.KEY:
        raise HTTPException(503, eleven.messages()[0])
    try:
        token = await eleven.realtime_token()
    except eleven.ElevenError as e:
        log.warning("token Scribe falhou: %s", e)
        if e.is_auth:
            eleven.STATUS["perms"]["realtime_token"] = False
        raise HTTPException(503, eleven.perm_message("realtime_token"))
    return {"token": token, "url": eleven.REALTIME_URL, "model_id": eleven.REALTIME_MODEL, "language_code": "pt", "sample_rate": 16000}


class ElevenVoiceIn(BaseModel):
    character: str
    voice: dict


@api.post("/scripts/{script_id}/eleven-voice")
async def set_eleven_voice(script_id: str, body: ElevenVoiceIn):
    if not eleven.KEY:
        raise HTTPException(400, "ElevenLabs não está configurado.")
    script = await get_script(script_id)
    for c in script.characters:
        if c.name == body.character:
            c.el_voice_id, c.el_voice_name = body.voice.get("id") or None, body.voice.get("name", "")
    await save_characters(script)
    return script_out(script)


@api.post("/scripts/{script_id}/auto-voices")
async def auto_eleven_voices(script_id: str):
    if not CATALOG["voices"]:
        raise HTTPException(404, (eleven.messages() or ["Sem vozes PT-PT disponíveis."])[0])
    script = await get_script(script_id)
    for c in script.characters:
        c.el_voice_id = None
    assign_default_eleven(script)
    await save_characters(script)
    return script_out(script)


@api.post("/tts")
async def tts(body: TTSIn):
    audio, provider, voice = await synth(body.text, body.voice, body.character, body.style, body.el_voice_id)
    return Response(content=audio, media_type="audio/mpeg", headers={
        "Cache-Control": "public, max-age=86400", "X-TTS-Provider": provider, "X-TTS-Voice": voice or ""})


STT_PROMPT = "Português de Portugal. Transcreve exactamente o que é dito, palavra a palavra."


async def transcribe(data: bytes, ext: str) -> str:
    if len(data) < 1000:
        return ""
    if ext not in OpenAISpeechToText.FILE_FORMATS:
        ext = "webm"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    engine = OpenAISpeechToText(api_key=LLM_KEY)

    async def run(model: str):
        with open(tmp_path, "rb") as f:
            kw = {"prompt": STT_PROMPT} if model != "whisper-1" else {"temperature": 0}
            r = await asyncio.wait_for(engine.transcribe(file=f, model=model, language="pt", **kw), timeout=10)
        t = r.text if hasattr(r, "text") else (r.get("text") if isinstance(r, dict) else str(r))
        return (t or "").strip()

    tasks = [asyncio.ensure_future(run(m)) for m in ("gpt-4o-mini-transcribe", "whisper-1")]
    text = ""
    try:
        for fut in asyncio.as_completed(tasks):
            try:
                text = await fut
            except Exception as e:
                log.warning("STT falhou: %s", e)
                continue
            if text:
                break
    finally:
        for t in tasks:
            t.cancel()
        os.unlink(tmp_path)
    if not norm_tokens(text) or "transcreve exactamente" in " ".join(norm_tokens(text)):
        return ""
    return text


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
        await save_characters(script)
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
    expected = effective_text(script, line)
    m = local_match(expected, said, 0.9 if session.strictness == "rigor" else 0.75)
    exp_tokens = norm_tokens(expected)
    notes = [" ".join(norm_tokens(n.text)) for n in script.memory if not n.new_text]
    in_memory = any(" ".join(exp_tokens[i:i + 4]) in n for n in notes for i in range(max(1, len(exp_tokens) - 3)))
    verdict = None if in_memory else fast_verdict(session.strictness, m, len(exp_tokens), said)
    note = None
    if verdict:
        _, severity = verdict
        turn = Turn(line_idx=line_idx, expected=expected, said=said, mode=mode, kind="line",
                    accuracy=m["accuracy"], severity=severity, differences=m["differences"])
    else:
        prev = next((ln for ln in reversed(script.lines[:line_idx]) if ln.kind == "dialogue"), None)
        prompt = (
            f"Instruções do actor: {session.instructions or '(nenhuma)'}\n"
            f"Memória do texto:\n{memory_block(script)}\n"
            f"Deixa anterior ({prev.character if prev else '-'}): {effective_text(script, prev) if prev else '-'}\n"
            f"Fala esperada ({line.character}): {expected}\n"
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
            line_idx=line_idx, expected=expected, said=said, mode=mode, kind=kind,
            accuracy=r.get("accuracy", m["accuracy"]) if kind == "line" else None, severity=r.get("severity", "none"),
            interrupted=bool(r.get("interrupt")) and kind == "line" and session.strictness != "nunca",
            feedback=r.get("feedback", "") or "",
            differences=r.get("differences", []) if kind == "line" else [],
        )
        if kind == "note" and r.get("memory_note"):
            note = MemoryNote(text=r["memory_note"])
            await db.scripts.update_one({"_id": oid(script.id)}, {"$push": {"memory": note.model_dump()}})
            asyncio.create_task(link_note_bg(script, note, line_idx))
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
    said = await transcribe(data, (file.filename or "a.webm").rsplit(".", 1)[-1].lower())
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
    async for d in db.scripts.find({"lines.uid": {"$exists": False}, "lines.0": {"$exists": True}}):
        lines = [{**ln, "uid": short_id()} for ln in d["lines"]]
        await db.scripts.update_one({"_id": d["_id"]}, {"$set": {"lines": lines}})
    if await db.scripts.count_documents({}) == 0:
        lines, chars = await build_structure(DEMO_TEXT)
        s = Script(title="A Espera", author="Cena de demonstração", raw_text=DEMO_TEXT, lines=lines, characters=chars)
        await db.scripts.insert_one(s.to_mongo())
    asyncio.create_task(eleven_bootstrap())


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-TTS-Provider", "X-TTS-Voice"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
