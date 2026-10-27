import os
import re
import io
import json
import uuid
import hashlib
import asyncio
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Annotated

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File  # noqa: E402
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
LLM_MODEL = ("anthropic", "claude-sonnet-5-5")
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
    start_idx: int = 0
    turns: List[Turn] = []
    status: str = "active"
    summary: Optional[dict] = None
    created_at: str = Field(default_factory=now)
    finished_at: Optional[str] = None


# ---------- LLM helpers ----------
async def ask_llm(system: str, prompt: str) -> str:
    chat = LlmChat(api_key=LLM_KEY, session_id=uuid.uuid4().hex, system_message=system).with_model(*LLM_MODEL)
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


class SessionIn(BaseModel):
    script_id: str
    character: str
    instructions: str = ""
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


@api.post("/tts")
async def tts(body: TTSIn):
    text = clean_for_tts(body.text)[:4000]
    if not text:
        raise HTTPException(400, "Texto vazio")
    voice = body.voice if body.voice in VOICES else PROMPTER_VOICE
    who = f"És um actor a dar voz à personagem {body.character}." if body.character else "És o apontador de um ensaio de teatro, calmo e claro."
    instructions = (
        "Fala SEMPRE em português europeu (português de Portugal), com pronúncia e sotaque de Lisboa; "
        "nunca uses sotaque brasileiro. Vogais átonas fechadas, 's' chiado no fim das palavras. "
        f"{who} {body.style} Interpreta de forma natural e teatral."
    )
    key = hashlib.sha256(f"{text}|{voice}|gpt-4o-mini-tts|mp3|{instructions}".encode()).hexdigest()
    path = TTS_CACHE / f"{key}.mp3"
    if not path.exists():
        engine = OpenAITextToSpeech(api_key=LLM_KEY)
        try:
            audio = await asyncio.wait_for(engine.generate_speech(
                text=text, model="gpt-4o-mini-tts", voice=voice, instructions=instructions), timeout=45)
        except Exception as e:
            log.warning("gpt-4o-mini-tts falhou (%s), a usar tts-1", e)
            fallback = voice if voice not in ("ballad", "verse") else "alloy"
            audio = await engine.generate_speech(text=text, model="tts-1", voice=fallback)
        path.write_bytes(audio)
    return Response(content=path.read_bytes(), media_type="audio/mpeg")


@api.post("/stt")
async def stt(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) < 1000:
        return {"text": ""}
    ext = (file.filename or "a.webm").rsplit(".", 1)[-1].lower()
    if ext not in OpenAISpeechToText.FILE_FORMATS:
        ext = "webm"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        engine = OpenAISpeechToText(api_key=LLM_KEY)
        with open(tmp_path, "rb") as f:
            res = await engine.transcribe(
                file=f, model="whisper-1", language="pt",
                prompt="Transcrição literal em português de Portugal, incluindo hesitações, repetições e enganos.")
    finally:
        os.unlink(tmp_path)
    text = getattr(res, "text", None) or (res.get("text") if isinstance(res, dict) else str(res))
    return {"text": (text or "").strip()}


# ---------- Sessions ----------
@api.post("/sessions")
async def create_session(body: SessionIn):
    script = await get_script(body.script_id)
    if body.character not in [c.name for c in script.characters]:
        raise HTTPException(400, "Personagem inválida")
    s = Session(**body.model_dump())
    res = await db.sessions.insert_one(s.to_mongo())
    s.id = str(res.inserted_id)
    return s.model_dump()


@api.get("/sessions/{session_id}")
async def read_session(session_id: str):
    return (await get_session(session_id)).model_dump()


TURN_SYSTEM = """És o apontador e treinador de texto de um actor profissional, num ensaio. Falas português de Portugal (PT-PT), nunca português do Brasil.
Recebes a fala que o actor devia dizer, o que ele efectivamente disse (transcrição automática de voz, que pode ter pequenos erros de reconhecimento, ou texto escrito), as instruções do actor sobre como queres que corrijas, e a memória do texto (alterações acordadas em ensaios anteriores, que SUBSTITUEM o texto original).

Classifica o que o actor disse:
- "line": tentou dizer a fala.
- "note": está a dar-te uma informação para memorizar sobre o texto (ex.: "aí mudámos nos ensaios, agora digo X em vez de Y", "corta esta frase").
- "help": está a pedir ajuda/deixa ("texto!", "linha", "como é que é?", "não me lembro").
- "other": outra coisa claramente dirigida a ti (comentário ou pergunta sobre o ensaio). Em caso de dúvida, ou se parecer uma tentativa de fala (mesmo muito errada ou sem relação com o texto), classifica como "line".

Para "line": compara com a fala esperada (considerando a memória), ignorando pontuação, maiúsculas, rubricas entre parêntesis e diferenças que sejam claramente erros da transcrição automática (homófonos, etc.). Lista TODAS as diferenças. Decide se deves interromper SEGUINDO RIGOROSAMENTE as instruções do actor. Se não houver instruções, interrompe apenas em erros graves (saltos grandes, sentido alterado, fala de outra personagem).

Responde APENAS com JSON:
{"kind":"line|note|help|other","accuracy":0-100,"severity":"none|minor|major","interrupt":true|false,
 "feedback":"frase curta e falada, em PT-PT, para dizer ao actor se interromperes (ex.: indicar o que falhou e a frase correcta), ou resposta à nota/pedido; vazio se não for preciso",
 "differences":[{"expected":"trecho esperado","said":"o que disse","type":"omissão|troca|acrescento|repetição|salto|inversão"}],
 "memory_note":"para kind=note: a nota a memorizar, redigida de forma clara e autónoma, citando a fala; senão vazio"}
Para "help": feedback deve dar as primeiras palavras da fala (ou mais, se pedido)."""


@api.post("/sessions/{session_id}/turn")
async def session_turn(session_id: str, body: TurnIn):
    session = await get_session(session_id)
    script = await get_script(session.script_id)
    if body.line_idx < 0 or body.line_idx >= len(script.lines):
        raise HTTPException(400, "Fala inválida")
    line = script.lines[body.line_idx]
    prev = next((ln for ln in reversed(script.lines[:body.line_idx]) if ln.kind == "dialogue"), None)
    prompt = (
        f"Texto: {script.title}\nPersonagem do actor: {session.character}\n"
        f"Instruções do actor: {session.instructions or '(nenhuma)'}\n"
        f"Memória do texto:\n{memory_block(script)}\n\n"
        f"Deixa anterior ({prev.character if prev else '-'}): {prev.text if prev else '-'}\n"
        f"Fala esperada ({line.character}): {line.text}\n\n"
        f"O actor disse ({body.mode}): {body.said}"
    )
    try:
        r = parse_json(await ask_llm(TURN_SYSTEM, prompt))
    except Exception as e:
        log.exception("avaliação falhou: %s", e)
        raise HTTPException(502, "Não consegui avaliar a fala. Tenta outra vez.")
    kind = r.get("kind", "line")
    turn = Turn(
        line_idx=body.line_idx, expected=line.text, said=body.said, mode=body.mode, kind=kind,
        accuracy=r.get("accuracy") if kind == "line" else None, severity=r.get("severity", "none"),
        interrupted=bool(r.get("interrupt")) and kind == "line", feedback=r.get("feedback", "") or "",
        differences=r.get("differences", []) if kind == "line" else [],
    )
    note = None
    if kind == "note" and r.get("memory_note"):
        note = MemoryNote(text=r["memory_note"])
        await db.scripts.update_one({"_id": oid(script.id)}, {"$push": {"memory": note.model_dump()}})
        if not turn.feedback:
            turn.feedback = "Anotado. Vou ter isso em conta."
    await db.sessions.update_one({"_id": oid(session_id)}, {"$push": {"turns": turn.model_dump()}})
    return {
        "turn": turn.model_dump(),
        "advance": kind == "line" and not turn.interrupted,
        "memory_note": note.model_dump() if note else None,
    }


SUMMARY_SYSTEM = """És um treinador de texto experiente para actores. Falas português de Portugal (PT-PT).
Recebes as falas que o actor ensaiou (texto esperado vs. o que disse, em cada tentativa), as instruções e a memória do texto (alterações acordadas que substituem o original).
Faz um resumo detalhado da prestação. É OBRIGATÓRIO listar TUDO o que foi diferente do texto fornecido (cada omissão, troca, acrescento, repetição, salto), mesmo pequenas coisas, ignorando apenas pontuação e erros evidentes de transcrição automática.
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
