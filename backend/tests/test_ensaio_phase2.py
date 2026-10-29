# Phase 2 (F-11..F-16) regression tests: STT tokens, Edge TTS, voices, phonetic matching, blocks, confirmation, finish
import os
import time
import pytest
import requests
from pathlib import Path


def _env(path, key):
    for ln in Path(path).read_text().splitlines():
        if ln.startswith(key + "="):
            return ln.split("=", 1)[1].strip().strip('"')
    return ""


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
DG_KEY = _env("/app/backend/.env", "DEEPGRAM_API_KEY")
GM_KEY = _env("/app/backend/.env", "GEMINI_API_KEY")

S = requests.Session()


def demo():
    r = S.get(f"{API}/scripts", timeout=20)
    r.raise_for_status()
    items = r.json()
    items = items if isinstance(items, list) else items.get("scripts", items.get("items", []))
    d = next(s for s in items if s["title"] == "A Espera")
    return S.get(f"{API}/scripts/{d['id']}", timeout=20).json()


def new_script(title, text):
    r = S.post(f"{API}/scripts", json={"title": title, "text": text}, timeout=60)
    assert r.status_code in (200, 201), r.text
    return r.json()


def session(script_id, character, strictness="grave"):
    r = S.post(f"{API}/sessions", json={"script_id": script_id, "character": character, "strictness": strictness}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def turn(sid, idx, said, idxs=None, mode="voz"):
    body = {"line_idx": idx, "said": said, "mode": mode}
    if idxs:
        body["line_idxs"] = idxs
    return S.post(f"{API}/sessions/{sid}/turn", json=body, timeout=60)


# --- Docs / STT engines / tokens
class TestSTT:
    def test_openapi(self):
        r = S.get(f"{API}/openapi.json", timeout=20)
        assert r.status_code == 200 and "paths" in r.json()

    def test_engines(self):
        d = S.get(f"{API}/stt/engines", timeout=20).json()
        assert d["order"] == ["deepgram", "gemini", "webspeech"]
        assert d["deepgram"] is True and d["gemini"] is True and d["messages"] == []

    def test_deepgram_token(self):
        r = S.post(f"{API}/stt/deepgram-token", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["token"] and d["url"] == "wss://api.deepgram.com/v1/listen"
        assert d["params"]["model"] == "nova-3" and d["params"]["language"] == "pt-PT"
        assert DG_KEY and DG_KEY not in r.text

    def test_gemini_token(self):
        r = S.post(f"{API}/stt/gemini-token", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["token"].startswith("auth_tokens/")
        assert "BidiGenerateContentConstrained" in d["url"]
        assert d["model"] == "gemini-3.5-transcribe-live"
        assert GM_KEY and GM_KEY not in r.text


# --- Voices / Edge TTS
class TestVoices:
    def test_voices_edge(self):
        d = S.get(f"{API}/voices", timeout=20).json()
        assert d["provider"] == "edge"
        ids = {v["id"] for v in d["edge"]}
        assert {"pt-PT-RaquelNeural", "pt-PT-DuarteNeural"} <= ids
        assert d["prompter"] == {"edge_voice": "pt-PT-RaquelNeural", "edge_pitch": 4, "edge_rate": 12}

    def test_demo_distinct_combos(self):
        chars = demo()["characters"]
        assert len(chars) == 3
        combos = [(c["edge_voice"], c["edge_pitch"], c["edge_rate"]) for c in chars]
        assert all(c["tts"] == "edge" and c["edge_voice"] for c in chars)
        assert len(set(combos)) == len(combos)

    def test_tts_character(self):
        r = S.post(f"{API}/tts", json={"text": "Olá, isto é um teste.", "character": "TEST_X", "edge_voice": "pt-PT-DuarteNeural",
                                        "edge_pitch": -12, "edge_rate": -6}, timeout=60)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("audio/mpeg") and len(r.content) > 1000
        assert r.headers["x-tts-provider"] == "edge"
        assert r.headers["x-tts-voice"] == "pt-PT-DuarteNeural -12Hz -6%"

    def test_tts_prompter(self):
        r = S.post(f"{API}/tts", json={"text": "Perdi-o. Ou melhor"}, timeout=60)
        assert r.status_code == 200
        assert r.headers["x-tts-provider"] == "edge"
        assert r.headers["x-tts-voice"] == "pt-PT-RaquelNeural +4Hz +12%"


class TestScriptVoices:
    @pytest.fixture(scope="class")
    def sc(self):
        s = new_script("TEST_P2 vozes", "ANA: Olá Rui.\nRUI: Olá Ana. Tudo bem?\nINÊS: Bom dia.\nPEDRO: Boa tarde.")
        yield s
        S.delete(f"{API}/scripts/{s['id']}")

    def test_new_script_auto_edge(self, sc):
        combos = [(c["edge_voice"], c["edge_pitch"], c["edge_rate"]) for c in sc["characters"]]
        assert all(c[0] for c in combos) and len(set(combos)) == len(combos)

    def test_invalid_edge_voice_400(self, sc):
        chars = [dict(c) for c in sc["characters"]]
        chars[0]["edge_voice"] = "pt-BR-FakeNeural"
        r = S.put(f"{API}/scripts/{sc['id']}", json={"characters": chars}, timeout=20)
        assert r.status_code == 400

    def test_pitch_rate_persist(self, sc):
        chars = [dict(c) for c in sc["characters"]]
        chars[0]["edge_pitch"], chars[0]["edge_rate"] = 17, -9
        r = S.put(f"{API}/scripts/{sc['id']}", json={"characters": chars}, timeout=20)
        assert r.status_code == 200, r.text
        got = S.get(f"{API}/scripts/{sc['id']}").json()["characters"][0]
        assert got["edge_pitch"] == 17 and got["edge_rate"] == -9

    def test_auto_voices(self, sc):
        r = S.post(f"{API}/scripts/{sc['id']}/auto-voices", timeout=20)
        assert r.status_code == 200
        chars = r.json()["characters"]
        combos = [(c["edge_voice"], c["edge_pitch"], c["edge_rate"]) for c in chars]
        assert len(set(combos)) == len(combos) and all(c["tts"] == "edge" for c in chars)
        assert ("pt-PT-RaquelNeural", 4, 12) not in combos


# --- Turn judging / phonetic matching / blocks / confirmation / summary
class TestTurns:
    def test_marta_line3_variant(self):
        sid = session(demo()["id"], "MARTA")
        r = turn(sid, 3, "Perdi o. Ou melhor, deixei-o ir. Fiquei a vê-lo afastar-se e não me mexi.")
        assert r.status_code == 200, r.text
        assert r.json()["advance"] is True

    def test_homophones(self):
        sc = new_script("TEST_P2 homo", "ANA: Ainda estás aqui? À espera.\nRUI: Sim.")
        try:
            sid = session(sc["id"], "ANA")
            t = turn(sid, 0, "Ainda tás aqui? Há espera.").json()
            assert t["advance"] is True
            assert t["turn"]["accuracy"] == 100 and t["turn"]["differences"] == []
        finally:
            S.delete(f"{API}/scripts/{sc['id']}")

    def test_meaning_change_reported(self):
        d = demo()
        sid = session(d["id"], "MARTA")
        # line 7 "Hoje é dia de pedra." -> omit; use line 5 with nunca/sempre-like change: replace "não sabia" by "sempre soube"
        t = turn(sid, 5, "Porque sempre soube que queria mesmo ir. Há dias em que partir parece a coisa mais fácil do mundo, e há outros em que pesa como uma pedra.")
        assert t.status_code == 200
        tj = t.json()
        assert tj["turn"]["differences"], tj
        f = S.post(f"{API}/sessions/{sid}/finish", timeout=120).json()
        diffs = f["summary"]["differences"]
        assert any("nao" in (x["expected"] + " " + x["said"]).lower() or "sempre" in x["said"].lower() for x in diffs), diffs

    def test_full_correct_readthrough(self):
        d = demo()
        sid = session(d["id"], "MARTA")
        lines = {ln["idx"]: ln["text"] for ln in d["lines"]}
        for i in (3, 5, 7, 10, 13, 15):
            r = turn(sid, i, lines[i])
            assert r.status_code == 200 and r.json()["advance"] is True, r.text
        f = S.post(f"{API}/sessions/{sid}/finish", timeout=120).json()
        s = f["summary"]
        assert s["differences"] == [] and s["score"] == 100
        assert "discarded" in s["stats"]

    def test_blocks(self):
        sc = new_script("TEST_P2 bloco", "ANA: Olá Rui.\nRUI: Olá Ana. Tudo bem?\nANA: Tudo. Cheguei agora.\n(Pausa.)\nANA: E tu, o que fazes aqui?\nRUI: Espero o comboio.")
        try:
            lines = sc["lines"]
            assert lines[2]["character"] == "ANA" and lines[4]["character"] == "ANA" and lines[3]["kind"] != "dialogue"
            sid = session(sc["id"], "ANA")
            t = turn(sid, 2, "Tudo. Cheguei agora. E tu, o que fazes aqui?", [2, 4]).json()
            assert t["turn"]["line_idxs"] == [2, 4]
            assert t["turn"]["expected"] == "Tudo. Cheguei agora. E tu, o que fazes aqui?"
            assert t["advance"] is True
            bad = turn(sid, 2, "x", [2, 5])
            assert bad.status_code == 400 and "Bloco inválido" in bad.text
        finally:
            S.delete(f"{API}/scripts/{sc['id']}")

    def test_background_confirmation(self):
        d = demo()
        sid = session(d["id"], "MARTA")
        t = turn(sid, 3, "Perdi-o. Ou melhor, deixei ir. Fiquei a ver afastar e não me mexi nada.").json()
        assert t["turn"]["differences"]
        tid = t["turn"]["id"]
        for _ in range(20):
            s = S.get(f"{API}/sessions/{sid}").json()
            tt = next(x for x in s["turns"] if x["id"] == tid)
            if tt["review"] == "done":
                break
            time.sleep(1)
        assert tt["review"] == "done"
        assert all(x["status"] in ("real", "discarded") for x in tt["differences"])
