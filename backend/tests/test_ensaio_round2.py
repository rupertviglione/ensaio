# Ensaio round 2: fast local matching, strictness, LLM path, voice-turn, ElevenLabs TTS/voices
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    for ln in open("/app/frontend/.env"):
        if ln.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = ln.split("=", 1)[1].strip()
API = f"{BASE_URL.rstrip('/')}/api"

FEMALE = {"EXAVITQu4vr4xnSDxMaL", "XrExE9yKIg1WjnnlVkGX", "FGY2WhTYpPnrIDTdsKH5", "XB0fDUnXU5powFXDhCwa",
          "cgSgspJ2msm6clMCkdW9", "pFZP5JQG7iQjIQuC4Bku", "Xb7hH8MSUJpSbSDYk0k2"}

COLLOQ = """TEST_R2 cena.

ANA: Vou prá casa, tá bem? Tou cansada.
PEDRO: Então vai. Eu fico aqui mais um bocado a pensar na vida.
ANA: Tens a certeza que não queres vir comigo para o jantar de logo à noite?
PEDRO: Tenho. Hoje preciso de estar sozinho com os meus pensamentos."""


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def demo(s):
    d = next(x for x in s.get(f"{API}/scripts").json() if x["title"] == "A Espera")
    return s.get(f"{API}/scripts/{d['id']}").json()


@pytest.fixture(scope="module")
def colloq(s):
    r = s.post(f"{API}/scripts", json={"title": "TEST_R2 coloquial", "text": COLLOQ})
    assert r.status_code == 200, r.text
    sc = r.json()
    yield sc
    s.delete(f"{API}/scripts/{sc['id']}")


def idx_of(script, starts):
    return next(ln["idx"] for ln in script["lines"] if ln["text"].startswith(starts))


def new_session(s, script, character, strictness, instructions=""):
    r = s.post(f"{API}/sessions", json={"script_id": script["id"], "character": character,
                                         "strictness": strictness, "instructions": instructions})
    assert r.status_code == 200, r.text
    assert r.json()["strictness"] == strictness
    return r.json()["id"]


def turn(s, sid, i, said, mode="escrito"):
    t0 = time.time()
    r = s.post(f"{API}/sessions/{sid}/turn", json={"line_idx": i, "said": said, "mode": mode})
    dt = time.time() - t0
    assert r.status_code == 200, r.text
    print(f"turn '{said[:40]}' -> {dt*1000:.0f}ms {r.json()['turn']['kind']} acc={r.json()['turn']['accuracy']} "
          f"adv={r.json()['advance']} int={r.json()['turn']['interrupted']} fb={r.json()['turn']['feedback'][:80]}")
    return r.json(), dt


# ---- Fast local matching ----
class TestFastMatch:
    def test_exact_no_punct_fast(self, s, demo):
        sid = new_session(s, demo, "MARTA", "grave")
        i = idx_of(demo, "Perdi-o")
        s.post(f"{API}/sessions/{sid}/turn", json={"line_idx": i, "said": "warmup"})  # warm
        r, dt = turn(s, sid, i, "perdi o ou melhor deixei o ir fiquei a ve lo afastar se e nao me mexi")
        assert r["advance"] is True and r["turn"]["severity"] == "none"
        assert r["turn"]["accuracy"] >= 97
        assert dt < 0.8, f"too slow {dt}"

    def test_digits_vs_words_rigor(self, s, demo):
        sid = new_session(s, demo, "CHEFE DA ESTAÇÃO", "rigor")
        i = idx_of(demo, "O último comboio")
        r, dt = turn(s, sid, i, "O último comboio prá Coimbra parte dentro de 10 minutos, linha 2")
        assert r["advance"] is True and r["turn"]["severity"] == "none" and r["turn"]["accuracy"] >= 97
        assert dt < 0.8

    def test_estas_tas_rigor(self, s, demo):
        sid = new_session(s, demo, "JOÃO", "rigor")
        i = idx_of(demo, "Ainda estás aqui")
        r, dt = turn(s, sid, i, "Ainda tás aqui? Pensei que já tivesses partido no comboio das 6")
        assert r["advance"] is True and r["turn"]["accuracy"] >= 97
        assert dt < 0.8

    def test_script_colloquial_user_says_formal(self, s, colloq):
        sid = new_session(s, colloq, "ANA", "rigor")
        i = idx_of(colloq, "Vou prá casa")
        r, dt = turn(s, sid, i, "Vou para casa, está bem? Estou cansada.")
        assert r["advance"] is True and r["turn"]["accuracy"] >= 97
        assert dt < 0.8

    def test_script_colloquial_user_says_colloquial(self, s, colloq):
        sid = new_session(s, colloq, "ANA", "rigor")
        i = idx_of(colloq, "Vou prá casa")
        r, _ = turn(s, sid, i, "Vou pra casa tá bem tou cansada")
        assert r["advance"] is True and r["turn"]["accuracy"] >= 97

    def test_para_o_pro(self, s, colloq):
        sid = new_session(s, colloq, "ANA", "rigor")
        i = idx_of(colloq, "Tens a certeza")
        r, dt = turn(s, sid, i, "Tens a certeza que não queres vir comigo pró jantar de logo à noite")
        assert r["advance"] is True and dt < 0.8


# ---- Strictness + LLM path ----
class TestStrictness:
    def test_nunca_never_interrupts(self, s, demo):
        sid = new_session(s, demo, "MARTA", "nunca")
        i = idx_of(demo, "Porque não sabia")
        r, dt = turn(s, sid, i, "Não sei, apetece-me batatas fritas.")
        assert r["advance"] is True and r["turn"]["interrupted"] is False
        assert dt < 0.8

    def test_rigor_real_difference_interrupts(self, s, demo):
        sid = new_session(s, demo, "MARTA", "rigor", "Modo rigoroso: interrompe quando eu trocar, saltar ou acrescentar palavras.")
        i = idx_of(demo, "Perdi-o")
        r, dt = turn(s, sid, i, "Perdi-o. Ou melhor, deixei-o partir. Fiquei a vê-lo afastar-se e não me mexi.")
        assert r["turn"]["kind"] == "line"
        assert r["turn"]["interrupted"] is True and r["advance"] is False
        assert r["turn"]["feedback"]

    def test_grave_major_error_interrupts(self, s, demo):
        sid = new_session(s, demo, "MARTA", "grave")
        i = idx_of(demo, "Porque não sabia")
        r, _ = turn(s, sid, i, "Porque sim. Gosto de comboios azuis e de bolos de chocolate.")
        assert r["turn"]["kind"] == "line" and r["turn"]["interrupted"] is True and r["turn"]["feedback"]

    def test_help(self, s, demo):
        sid = new_session(s, demo, "MARTA", "grave")
        r, _ = turn(s, sid, idx_of(demo, "Porque não sabia"), "texto!")
        assert r["turn"]["kind"] == "help" and r["advance"] is False and r["turn"]["feedback"]

    def test_note_saved(self, s, demo):
        sid = new_session(s, demo, "MARTA", "grave")
        r, _ = turn(s, sid, idx_of(demo, "A tua avó"), "aí mudámos nos ensaios, agora digo 'a tua avó era muito sábia' em vez de 'uma mulher sábia'")
        assert r["turn"]["kind"] == "note" and r["advance"] is False
        assert r["memory_note"] and r["memory_note"]["text"]
        mem = s.get(f"{API}/scripts/{demo['id']}").json()["memory"]
        assert any(m["id"] == r["memory_note"]["id"] for m in mem)
        s.delete(f"{API}/scripts/{demo['id']}/memory/{r['memory_note']['id']}")

    def test_help_in_nunca_mode(self, s, demo):
        # 'nunca' skips LLM entirely: help/note requests may be swallowed as lines
        sid = new_session(s, demo, "MARTA", "nunca")
        r, _ = turn(s, sid, idx_of(demo, "Porque não sabia"), "texto!")
        assert r["turn"]["kind"] == "help", "help request in 'nunca' mode was accepted as a line and advanced"


# ---- Voice turn ----
class TestVoiceTurn:
    def test_silent_returns_null(self, s, demo):
        sid = new_session(s, demo, "MARTA", "grave")
        r = s.post(f"{API}/sessions/{sid}/voice-turn", data={"line_idx": idx_of(demo, "Perdi-o")},
                   files={"file": ("a.webm", b"\x00" * 200, "audio/webm")})
        assert r.status_code == 200
        assert r.json()["turn"] is None and r.json()["advance"] is False

    def test_real_audio(self, s, demo):
        i = idx_of(demo, "Porque não sabia")
        text = demo["lines"][i]["text"]
        audio = s.post(f"{API}/tts", json={"text": text, "el_voice_id": "XrExE9yKIg1WjnnlVkGX"}).content
        sid = new_session(s, demo, "MARTA", "grave")
        t0 = time.time()
        r = s.post(f"{API}/sessions/{sid}/voice-turn", data={"line_idx": i},
                   files={"file": ("a.mp3", audio, "audio/mpeg")})
        print("voice-turn", time.time() - t0, r.json().get("said"))
        assert r.status_code == 200
        d = r.json()
        assert d["said"] and d["turn"]["mode"] == "voz" and d["advance"] is True

    def test_bad_idx(self, s, demo):
        sid = new_session(s, demo, "MARTA", "grave")
        r = s.post(f"{API}/sessions/{sid}/voice-turn", data={"line_idx": 999},
                   files={"file": ("a.webm", b"\x00" * 2000, "audio/webm")})
        assert r.status_code == 400


# ---- ElevenLabs ----
class TestEleven:
    def test_voices(self, s):
        d = s.get(f"{API}/voices").json()
        assert d["provider"] == "elevenlabs"
        assert len(d["elevenlabs"]) >= 10 and all("id" in v for v in d["elevenlabs"])

    def test_tts_el_fast(self, s):
        txt = f"Teste rápido número {int(time.time())}."
        t0 = time.time()
        r = s.post(f"{API}/tts", json={"text": txt, "el_voice_id": "JBFqnCBsd6RMkjVDRZzb", "character": "JOÃO"})
        dt = time.time() - t0
        print("EL tts", dt)
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 1000
        assert dt < 3

    def test_tts_openai_fallback(self, s):
        r = s.post(f"{API}/tts", json={"text": f"Sem voz eleven {int(time.time())}.", "voice": "onyx", "character": "JOÃO"})
        assert r.status_code == 200 and len(r.content) > 1000

    def test_tts_prompter(self, s):
        t0 = time.time()
        r = s.post(f"{API}/tts", json={"text": f"Apontador {int(time.time())}."})
        print("prompter tts", time.time() - t0)
        assert r.status_code == 200 and len(r.content) > 1000

    def test_auto_voices_gender(self, s, colloq):
        r = s.post(f"{API}/scripts/{colloq['id']}/auto-voices")
        assert r.status_code == 200
        ch = {c["name"]: c for c in r.json()["characters"]}
        assert ch["ANA"]["el_voice_id"] in FEMALE
        assert ch["PEDRO"]["el_voice_id"] not in FEMALE and ch["PEDRO"]["el_voice_id"]

    def test_set_eleven_voice(self, s, colloq):
        r = s.post(f"{API}/scripts/{colloq['id']}/eleven-voice",
                   json={"character": "PEDRO", "voice": {"id": "onwK4e9ZLuTAKqWVaz9q", "name": "Daniel", "owned": True}})
        assert r.status_code == 200
        got = next(c for c in s.get(f"{API}/scripts/{colloq['id']}").json()["characters"] if c["name"] == "PEDRO")
        assert got["el_voice_id"] == "onwK4e9ZLuTAKqWVaz9q" and got["el_voice_name"] == "Daniel"

    def test_session_autoassigns(self, s, colloq):
        sc = s.get(f"{API}/scripts/{colloq['id']}").json()
        chars = [{**c, "el_voice_id": None, "el_voice_name": ""} for c in sc["characters"]]
        assert s.put(f"{API}/scripts/{colloq['id']}", json={"characters": chars}).status_code == 200
        new_session(s, colloq, "ANA", "grave")
        after = s.get(f"{API}/scripts/{colloq['id']}").json()["characters"]
        assert all(c["el_voice_id"] for c in after)
