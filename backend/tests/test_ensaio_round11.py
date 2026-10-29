# Round 11: Edge-primary TTS (no automatic ElevenLabs), non-blocking pre-generation, re-pregen on voice change
import os, time, uuid, pytest, requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
SID = "6ae30c5e951be2df4653fc9d"  # A Espera
LOG = "/var/log/supervisor/backend.err.log"


def log_size():
    return os.path.getsize(LOG)


def log_since(off):
    with open(LOG, "rb") as f:
        f.seek(off)
        return f.read().decode("utf-8", "replace")


def wait_log(off, needle, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        txt = log_since(off)
        if needle in txt:
            return txt, time.time() - t0
        time.sleep(0.25)
    return log_since(off), None


# --- primary provider
class TestPrimary:
    def test_tts_status_default_edge(self):
        r = requests.get(f"{API}/tts/status", timeout=20)
        assert r.status_code == 200
        assert r.json()["default"] == "edge"

    def test_settings_keys_primary_edge(self):
        r = requests.get(f"{API}/settings/keys", timeout=20)
        assert r.status_code == 200
        assert r.json()["tts_primary"] == "edge"

    def test_voices_provider_edge(self):
        assert requests.get(f"{API}/voices", timeout=20).json()["provider"] == "edge"


# --- POST /api/tts for 'auto' characters → Edge, no ElevenLabs traffic
class TestTTSAuto:
    def test_auto_chars_use_edge(self):
        sc = requests.get(f"{API}/scripts/{SID}", timeout=20).json()
        off = log_size()
        for c in sc["characters"]:
            assert c["tts"] == "auto", c
            body = {"text": f"Teste de voz {uuid.uuid4().hex[:5]} para {c['name']}.", "character": c["name"], "voice": c["voice"],
                    "tts": "auto", "el_voice_id": c["el_voice_id"], "edge_voice": c["edge_voice"],
                    "edge_pitch": c["edge_pitch"], "edge_rate": c["edge_rate"], "script_id": SID}
            r = requests.post(f"{API}/tts", json=body, timeout=60)
            assert r.status_code == 200, r.text
            assert r.headers.get("X-TTS-Provider") == "edge", r.headers
            assert r.headers.get("content-type", "").startswith("audio/mpeg")
            assert len(r.content) > 1000
        time.sleep(1)
        assert "api.elevenlabs.io" not in log_since(off)

    def test_prompter_uses_edge(self):
        r = requests.post(f"{API}/tts", json={"text": f"Dica {uuid.uuid4().hex[:4]}"}, timeout=60)
        assert r.status_code == 200
        assert r.headers.get("X-TTS-Provider") == "edge"


# --- session creation triggers fast pre-generation; PUT characters re-pregen
class TestPregen:
    def test_session_pregen_edge_only(self):
        off = log_size()
        t0 = time.time()
        r = requests.post(f"{API}/sessions", json={"script_id": SID, "character": "MARTA"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["id"]
        print("session create took", round(time.time() - t0, 2))
        txt, dt = wait_log(off, "pré-geração:")
        assert dt is not None, "no pré-geração log line"
        line = [l for l in txt.splitlines() if "pré-geração:" in l][0]
        print("PREGEN", round(dt, 2), line)
        assert " 0 ElevenLabs" in line and " 0 falhas" in line
        assert dt < 15
        time.sleep(1)
        assert "api.elevenlabs.io" not in log_since(off)

    def test_bad_character_400(self):
        r = requests.post(f"{API}/sessions", json={"script_id": SID, "character": "TEST_NOBODY"}, timeout=30)
        assert r.status_code == 400

    def test_put_characters_repregen(self):
        sc = requests.get(f"{API}/scripts/{SID}", timeout=20).json()
        orig = [dict(c) for c in sc["characters"]]
        chars = [dict(c) for c in orig]
        chars[1]["edge_rate"] = (chars[1]["edge_rate"] or 0) + 3
        off = log_size()
        try:
            r = requests.put(f"{API}/scripts/{SID}", json={"characters": chars}, timeout=30)
            assert r.status_code == 200, r.text
            assert [c for c in r.json()["characters"] if c["name"] == chars[1]["name"]][0]["edge_rate"] == chars[1]["edge_rate"]
            txt, dt = wait_log(off, "pré-geração:", 60)
            assert dt is not None, "no re-pregen after PUT characters"
            line = [l for l in txt.splitlines() if "pré-geração:" in l][0]
            print("REPREGEN", round(dt, 2), line)
            assert " 0 ElevenLabs" in line
            assert "api.elevenlabs.io" not in log_since(off)
        finally:
            off2 = log_size()
            r = requests.put(f"{API}/scripts/{SID}", json={"characters": orig}, timeout=30)
            assert r.status_code == 200
            wait_log(off2, "pré-geração:", 60)

    def test_put_invalid_voice_400(self):
        sc = requests.get(f"{API}/scripts/{SID}", timeout=20).json()
        chars = [dict(c) for c in sc["characters"]]
        chars[0]["edge_voice"] = "xx-BOGUS"
        r = requests.put(f"{API}/scripts/{SID}", json={"characters": chars}, timeout=30)
        assert r.status_code == 400
