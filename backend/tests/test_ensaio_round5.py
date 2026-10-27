# Round 5: pt-PT ElevenLabs catalog, status/permissions, Scribe token, hint_seconds, pre-generation, TTS providers/fallback/long text, probe removed, turn regression
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DEMO_ID = next(x["id"] for x in requests.get(f"{API}/scripts").json() if x["title"] == "A Espera")
JOANA = "nJ5NFqyKb8kn9JBPmo6i"
EXPECTED_DEMO = {"JOÃO": "RlGHmE2fztwdBDat0jYf", "MARTA": "bBNhdwrIjl4fcVYiRbT2", "CHEFE DA ESTAÇÃO": "pjqwOzrEUZ3n3m4rMWWL"}
BR_IDS = {"JBFqnCBsd6RMkjVDRZzb", "EXAVITQu4vr4xnSDxMaL"}
LOG = "/var/log/supervisor/backend.err.log"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def demo(s):
    r = s.get(f"{API}/scripts/{DEMO_ID}")
    assert r.status_code == 200
    return r.json()


def no_key(text):
    assert not re.search(r"sk_[A-Za-z0-9]{10,}", text), "ElevenLabs key leaked"


# --- docs
def test_openapi_and_docs(s):
    assert s.get(f"{API}/openapi.json").status_code == 200
    assert s.get(f"{API}/docs").status_code == 200


# --- eleven status
def test_eleven_status(s):
    r = s.get(f"{API}/eleven/status")
    assert r.status_code == 200
    no_key(r.text)
    d = r.json()
    assert d["valid"] is True
    p = d["permissions"]
    assert p["tts"] is True and p["stt"] is True and p["realtime_token"] is True
    assert p["voices_read"] is False
    assert any("sem permissão para ler vozes (Voices: Read)" in m for m in d["messages"])
    cat = d["catalog"]
    assert len(cat) == 9
    assert sum(v["gender"] == "female" for v in cat) == 4
    assert sum(v["gender"] == "male" for v in cat) == 5
    assert d["prompter"]["id"] == JOANA and d["prompter"]["name"] == "Joana"


def test_stt_token(s):
    r = s.post(f"{API}/stt/token")
    assert r.status_code == 200, r.text
    no_key(r.text)
    d = r.json()
    assert d["token"].startswith("sutkn_")
    assert d["url"] == "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
    assert d["model_id"] == "scribe_v2_realtime" and d["language_code"] == "pt" and d["sample_rate"] == 16000


def test_voices(s):
    d = s.get(f"{API}/voices").json()
    st = s.get(f"{API}/eleven/status").json()
    assert d["provider"] == "elevenlabs" and d["pt_native"] is True
    assert d["elevenlabs"] == st["catalog"]
    assert isinstance(d["messages"], list)


def test_demo_voices(demo):
    chars = {c["name"]: c for c in demo["characters"]}
    for name, vid in EXPECTED_DEMO.items():
        assert chars[name]["el_voice_id"] == vid, (name, chars[name])
    ids = [c["el_voice_id"] for c in demo["characters"]]
    assert len(set(ids)) == len(ids)
    assert not (set(ids) & BR_IDS)


# --- sessions hint_seconds
@pytest.mark.parametrize("hs,code", [(2, 422), (16, 422), (10, 200)])
def test_hint_seconds_validation(s, hs, code):
    r = s.post(f"{API}/sessions", json={"script_id": DEMO_ID, "character": "MARTA", "hint_seconds": hs})
    assert r.status_code == code
    if code == 200:
        sid = r.json()["id"]
        assert s.get(f"{API}/sessions/{sid}").json()["hint_seconds"] == 10


def test_hint_default_and_pregeneration(s, demo):
    r = s.post(f"{API}/sessions", json={"script_id": DEMO_ID, "character": "MARTA"})
    assert r.status_code == 200
    assert r.json()["hint_seconds"] == 5
    found = False
    for _ in range(15):
        time.sleep(1)
        tail = open(LOG, encoding="utf-8", errors="ignore").read()[-300000:]
        m = re.findall(r"pré-geração: (\d+) falas IA \((\d+) falhas, (\d+) ElevenLabs\)", tail)
        if m:
            n, f, e = m[-1]
            print("pregen:", m[-1])
            assert f == "0" and n == e
            found = True
            break
    assert found, "pré-geração log not found"
    # cached AI line must be fast + elevenlabs
    chars = {c["name"]: c for c in demo["characters"]}
    ln = next(x for x in demo["lines"] if x["character"] == "JOÃO")
    c = chars["JOÃO"]
    t0 = time.time()
    r = s.post(f"{API}/tts", json={"text": ln["edited_text"] or ln["text"], "voice": c["voice"], "character": "JOÃO",
                                   "style": c["style"], "el_voice_id": c["el_voice_id"]})
    dt = time.time() - t0
    print("cached tts roundtrip", round(dt, 3))
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/mpeg")
    assert r.headers["X-TTS-Provider"] == "elevenlabs" and r.headers["X-TTS-Voice"] == c["el_voice_id"]
    assert dt < 1.5


def test_prompter_tts(s):
    r = s.post(f"{API}/tts", json={"text": "Perdi-o. Ou melhor"})
    assert r.status_code == 200
    assert r.headers["X-TTS-Provider"] == "elevenlabs" and r.headers["X-TTS-Voice"] == JOANA


def test_long_text_no_truncation(s):
    base = ("A estação estava quase vazia quando o último comboio chegou, e ninguém sabia ao certo quem ia partir. "
            "Havia malas esquecidas, bilhetes amarrotados e uma luz amarela que tornava tudo mais lento. ")
    short = s.post(f"{API}/tts", json={"text": base + "Fim curto número um.", "character": "MARTA", "el_voice_id": EXPECTED_DEMO["MARTA"]}, timeout=120)
    long_text = (base * 11) + "Fim longo número um."
    assert len(long_text) > 2000
    t0 = time.time()
    r = s.post(f"{API}/tts", json={"text": long_text, "character": "MARTA", "el_voice_id": EXPECTED_DEMO["MARTA"]}, timeout=180)
    print("long tts", round(time.time() - t0, 1), "s", len(short.content), len(r.content))
    assert r.status_code == 200
    assert r.headers["X-TTS-Provider"] == "elevenlabs" and r.headers["X-TTS-Voice"] == EXPECTED_DEMO["MARTA"]
    ratio = len(r.content) / len(short.content)
    print("ratio", ratio)
    assert ratio > 7  # ~11x text => audio should be much larger


def test_fallback_openai(s):
    r = s.post(f"{API}/tts", json={"text": f"Teste de recurso {int(time.time())}.", "character": "JOÃO",
                                   "voice": "onyx", "el_voice_id": "invalidVoiceId000000"}, timeout=90)
    assert r.status_code == 200 and len(r.content) > 2000
    assert r.headers["X-TTS-Provider"] == "openai"
    time.sleep(1)
    assert "TTS FALLBACK OpenAI" in open(LOG, encoding="utf-8", errors="ignore").read()[-300000:]


def test_tts_premade_id_ignored(s):
    r = s.post(f"{API}/tts", json={"text": "Olá Marta.", "character": "JOÃO", "voice": "onyx", "el_voice_id": "JBFqnCBsd6RMkjVDRZzb"}, timeout=90)
    assert r.status_code == 200
    print("premade ->", r.headers["X-TTS-Provider"], r.headers["X-TTS-Voice"])
    assert r.headers["X-TTS-Voice"] != "JBFqnCBsd6RMkjVDRZzb"


# --- probe removed + turn regression
@pytest.fixture(scope="module")
def sess(s):
    def make(strict):
        r = s.post(f"{API}/sessions", json={"script_id": DEMO_ID, "character": "MARTA", "strictness": strict})
        return r.json()["id"]
    return make


def test_probe_removed(s, sess):
    sid = sess("grave")
    r = s.post(f"{API}/sessions/{sid}/probe", data={"line_idx": "3"}, files={"file": ("a.webm", b"\x00" * 100, "audio/webm")})
    assert r.status_code in (404, 405)


@pytest.mark.parametrize("strict", ["grave", "rigor", "nunca"])
def test_turn_correct(s, sess, demo, strict):
    sid = sess(strict)
    ln = demo["lines"][3]
    r = s.post(f"{API}/sessions/{sid}/turn", json={"line_idx": 3, "said": ln["edited_text"] or ln["text"], "mode": "texto"})
    assert r.status_code == 200 and r.json()["advance"] is True


def test_turn_rigor_swap(s, sess, demo):
    # without actor instructions the LLM treats a single swap as minor (pre-existing behaviour), so pass rigor instructions
    sid = s.post(f"{API}/sessions", json={"script_id": DEMO_ID, "character": "MARTA", "strictness": "rigor",
                                          "instructions": "Modo rigoroso: interrompe quando eu trocar, saltar ou acrescentar palavras."}).json()["id"]
    said = "Perdi-o. Ou melhor, deixei-o partir. Fiquei a vê-lo afastar-se e não me mexi."
    r = s.post(f"{API}/sessions/{sid}/turn", json={"line_idx": 3, "said": said, "mode": "texto"}, timeout=60)
    assert r.status_code == 200
    d = r.json()
    print("rigor swap", d["advance"], d["turn"]["feedback"])
    assert d["advance"] is False and d["turn"]["interrupted"] is True


def test_turn_nunca_wrong_advances(s, sess):
    sid = sess("nunca")
    r = s.post(f"{API}/sessions/{sid}/turn", json={"line_idx": 3, "said": "Perdi o comboio e fiquei aqui", "mode": "texto"}, timeout=60)
    assert r.status_code == 200 and r.json()["turn"]["interrupted"] is False


# --- regression
def test_create_update_memory_finish(s):
    text = "ANA: Bom dia, Rui. Hoje está frio.\nRUI: Está mesmo. Trouxeste o casaco?\nANA: Trouxe, claro."
    r = s.post(f"{API}/scripts", json={"title": "TEST_R5", "text": text})
    assert r.status_code == 200
    sc = r.json()
    try:
        chars = {c["name"]: c for c in sc["characters"]}
        assert set(chars) == {"ANA", "RUI"}
        assert all(c["el_voice_id"] for c in chars.values())
        assert chars["ANA"]["el_voice_id"] != chars["RUI"]["el_voice_id"]
        assert s.get(f"{API}/scripts").status_code == 200
        ch = sc["characters"]
        ch[0]["voice"] = "nova"
        r = s.put(f"{API}/scripts/{sc['id']}", json={"characters": ch})
        assert r.status_code == 200 and r.json()["characters"][0]["voice"] == "nova"
        r = s.post(f"{API}/scripts/{sc['id']}/memory", json={"text": "nota", "line_idx": 0, "new_text": "Bom dia, Rui. Que frio."})
        assert r.status_code == 200
        assert s.get(f"{API}/scripts/{sc['id']}").json()["lines"][0]["edited_text"] == "Bom dia, Rui. Que frio."
        sid = s.post(f"{API}/sessions", json={"script_id": sc["id"], "character": "ANA"}).json()["id"]
        s.post(f"{API}/sessions/{sid}/turn", json={"line_idx": 0, "said": "Bom dia, Rui. Que frio.", "mode": "texto"})
        r = s.post(f"{API}/sessions/{sid}/finish", timeout=120)
        assert r.status_code == 200 and r.json()["status"] == "finished" and r.json()["summary"]
        f = s.post(f"{API}/extract", files={"file": ("a.txt", text.encode(), "text/plain")})
        assert f.status_code == 200 and "Trouxeste" in f.json()["text"]
    finally:
        s.delete(f"{API}/scripts/{sc['id']}")
