# Round 4: OpenAI default voices, ElevenLabs ID set/clear, STT (no prompt, silence), /probe completion detection, rename no-op
import io
import os
import sys
import time
import wave
import pytest
import requests

pytestmark = pytest.mark.skip(reason="Obsolete since round 5: /probe removed, server.is_complete removed, pt-PT ElevenLabs catalog auto-assigned (see test_ensaio_round5.py)")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
sys.path.insert(0, "/app/backend")

MARTA3 = "Perdi-o. Ou melhor, deixei-o ir. Fiquei a vê-lo afastar-se e não me mexi."
PARTIAL = "Perdi-o. Ou melhor, deixei-o ir."


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def script(s):
    from server import DEMO_TEXT
    r = s.post(f"{API}/scripts", json={"title": "TEST_R4 api", "text": DEMO_TEXT})
    assert r.status_code == 200, r.text
    d = r.json()
    yield d
    s.delete(f"{API}/scripts/{d['id']}")


@pytest.fixture(scope="module")
def session(s, script):
    r = s.post(f"{API}/sessions", json={"script_id": script["id"], "character": "MARTA", "strictness": "grave"})
    assert r.status_code == 200, r.text
    return r.json()


def tts(s, text):
    r = s.post(f"{API}/tts", json={"text": text})
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/mpeg")
    assert len(r.content) > 3000
    return r.content


def silent_wav(sec=2.0):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * sec))
    return buf.getvalue()


# --- voices
def test_voices_list(s):
    d = s.get(f"{API}/voices").json()
    assert d["provider"] == "elevenlabs"
    assert d["elevenlabs"] == []
    assert d.get("pt_native") is False
    assert "sage" in d["openai"]


def test_new_script_no_el_voice(script):
    assert script["lines"][3]["character"] == "MARTA" and script["lines"][3]["text"] == MARTA3
    assert all(not c.get("el_voice_id") for c in script["characters"])


def test_demo_premade_cleared(s):
    for d in s.get(f"{API}/scripts").json():
        for c in d["characters"]:
            assert c.get("el_voice_id") not in ("JBFqnCBsd6RMkjVDRZzb", "EXAVITQu4vr4xnSDxMaL", "onwK4e9ZLuTAKqWVaz9q")


def test_auto_voices_404(s, script):
    r = s.post(f"{API}/scripts/{script['id']}/auto-voices")
    assert r.status_code == 404
    assert "Voices: Read" in r.json()["detail"]


def test_eleven_voice_set_and_clear(s, script):
    sid = script["id"]
    r = s.post(f"{API}/scripts/{sid}/eleven-voice", json={"character": "JOÃO", "voice": {"id": "abc123TEST", "name": "abc123TEST", "owned": True}})
    assert r.status_code == 200
    c = next(x for x in r.json()["characters"] if x["name"] == "JOÃO")
    assert c["el_voice_id"] == "abc123TEST"
    r = s.post(f"{API}/scripts/{sid}/eleven-voice", json={"character": "JOÃO", "voice": {"id": None}})
    c = next(x for x in s.get(f"{API}/scripts/{sid}").json()["characters"] if x["name"] == "JOÃO")
    assert c["el_voice_id"] is None


def test_prompter_tts(s):
    tts(s, "Atenção, falta uma palavra.")


# --- STT
def test_stt_tiny_and_silence(s):
    r = s.post(f"{API}/stt", files={"file": ("a.webm", b"\x00" * 200, "audio/webm")})
    assert r.status_code == 200 and r.json()["text"] == ""
    r = s.post(f"{API}/stt", files={"file": ("a.wav", silent_wav(), "audio/wav")})
    assert r.status_code == 200
    print("silence ->", repr(r.json()["text"]))
    assert r.json()["text"] == ""


def test_stt_real_speech(s):
    audio = tts(s, MARTA3)
    t0 = time.time()
    r = s.post(f"{API}/stt", files={"file": ("a.mp3", audio, "audio/mpeg")})
    print("stt latency", round(time.time() - t0, 2), r.json())
    assert r.status_code == 200
    txt = r.json()["text"].lower()
    assert "mexi" in txt and "perdi" in txt


# --- probe
def test_probe_partial_not_complete(s, session):
    sid = session["id"]
    audio = tts(s, PARTIAL)
    r = s.post(f"{API}/sessions/{sid}/probe", data={"line_idx": "3", "final": "false"}, files={"file": ("a.mp3", audio, "audio/mpeg")})
    assert r.status_code == 200, r.text
    d = r.json()
    print("partial ->", d)
    assert d["complete"] is False and d["said"]
    assert "turn" not in d or d["turn"] is None
    assert s.get(f"{API}/sessions/{sid}").json()["turns"] == []


def test_probe_full_complete(s, session):
    sid = session["id"]
    audio = tts(s, MARTA3)
    t0 = time.time()
    r = s.post(f"{API}/sessions/{sid}/probe", data={"line_idx": "3", "final": "false"}, files={"file": ("a.mp3", audio, "audio/mpeg")})
    print("probe full latency", round(time.time() - t0, 2))
    d = r.json()
    print("full ->", d)
    assert d["complete"] is True and d["advance"] is True
    assert d["turn"]["line_idx"] == 3 and d["turn"]["accuracy"] >= 80
    turns = s.get(f"{API}/sessions/{sid}").json()["turns"]
    assert len(turns) == 1


def test_probe_partial_final_evaluates(s, session):
    sid = session["id"]
    audio = tts(s, PARTIAL)
    r = s.post(f"{API}/sessions/{sid}/probe", data={"line_idx": "3", "final": "true"}, files={"file": ("a.mp3", audio, "audio/mpeg")})
    d = r.json()
    print("final partial ->", d.get("turn", {}).get("accuracy"), d.get("advance"), d.get("turn", {}).get("feedback"))
    assert d["complete"] is True and d["turn"] is not None
    assert d["turn"]["accuracy"] < 80
    assert len(s.get(f"{API}/sessions/{sid}").json()["turns"]) == 2


def test_probe_silence_and_invalid(s, session):
    sid = session["id"]
    r = s.post(f"{API}/sessions/{sid}/probe", data={"line_idx": "3", "final": "false"}, files={"file": ("a.wav", silent_wav(), "audio/wav")})
    assert r.json()["complete"] is False and r.json()["said"] == ""
    r = s.post(f"{API}/sessions/{sid}/probe", data={"line_idx": "3", "final": "true"}, files={"file": ("a.webm", b"\x00" * 100, "audio/webm")})
    assert r.json()["complete"] is True and r.json()["turn"] is None
    r = s.post(f"{API}/sessions/{sid}/probe", data={"line_idx": "999"}, files={"file": ("a.webm", b"\x00" * 100, "audio/webm")})
    assert r.status_code == 400


# --- is_complete unit (server + client semantics)
@pytest.mark.parametrize("said,exp", [
    (MARTA3, True),
    ("perdi o ou melhor deixei o ir fiquei a ve lo afastar se e nao me mexi", True),
    (PARTIAL, False),
    ("Perdi-o. Ou melhor, deixei-o ir. Fiquei a vê-lo", False),
    ("não me mexi", False),
    ("Perdi-o, deixei-o ir, fiquei a vê-lo afastar e não me mexi", True),
])
def test_is_complete_unit(said, exp):
    from server import is_complete
    assert is_complete(MARTA3, said) is exp


# --- iteration-3 fixes
def test_rename_same_name_noop(s, script):
    sid = script["id"]
    r = s.post(f"{API}/scripts/{sid}/rename-character", json={"old": "MARTA", "new": "marta"})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["characters"]]
    assert "MARTA" in names and len(names) == 3
