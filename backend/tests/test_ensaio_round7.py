# Round 7: settings keys, Deepgram WS proxy, auto-marked non-script text, pronunciation, matching, TTS
import asyncio
import json
import os
import sys

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ENV = dotenv_values("/app/backend/.env")
sys.path.insert(0, "/app/backend")


def scripts():
    d = requests.get(f"{API}/scripts", timeout=30).json()
    return d if isinstance(d, list) else d.get("scripts", d)


def find(title):
    for s in scripts():
        if s["title"] == title:
            return s["id"]
    pytest.skip(f"{title} not found")


created = []


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for sid in created:
        requests.delete(f"{API}/scripts/{sid}", timeout=30)


# ---------- Settings keys ----------
class TestSettings:
    def test_get_keys_masked(self):
        r = requests.get(f"{API}/settings/keys", timeout=30)
        assert r.status_code == 200
        body = r.text
        d = r.json()
        provs = {k["provider"]: k for k in d["keys"]}
        assert set(provs) == {"elevenlabs", "deepgram", "gemini"}
        for p, k in provs.items():
            assert k["configured"] is True
            assert len(k["last4"]) == 4
        for name in ("ELEVENLABS_API_KEY", "DEEPGRAM_API_KEY", "GEMINI_API_KEY", "EMERGENT_LLM_KEY"):
            v = (ENV.get(name) or "").strip()
            if v:
                assert v not in body, f"full {name} leaked"
        assert d["tts_primary"] in ("edge", "elevenlabs")

    def test_validate_invalid_deepgram_dry_run(self):
        before = {k["provider"]: k for k in requests.get(f"{API}/settings/keys", timeout=30).json()["keys"]}
        r = requests.post(f"{API}/settings/keys/deepgram/validate", json={"key": "abc123"}, timeout=40)
        assert r.status_code == 200
        d = r.json()
        assert d["attempt"]["valid"] is False and d["saved"] is False
        g = {k["provider"]: k for k in requests.get(f"{API}/settings/keys", timeout=30).json()["keys"]}
        assert (g["deepgram"]["last4"], g["deepgram"]["source"]) == (before["deepgram"]["last4"], before["deepgram"]["source"])

    def test_check_deepgram_valid(self):
        r = requests.post(f"{API}/settings/keys/deepgram/check", timeout=40)
        assert r.status_code == 200
        d = r.json()
        assert d["status"]["valid"] is True
        print("deepgram status:", {k: v for k, v in d["status"].items() if k != "key"})

    def test_check_gemini_valid(self):
        r = requests.post(f"{API}/settings/keys/gemini/check", timeout=40)
        assert r.status_code == 200
        assert r.json()["status"]["valid"] is True

    def test_validate_invalid_elevenlabs_dry_run(self):
        before = {k["provider"]: k for k in requests.get(f"{API}/settings/keys", timeout=30).json()["keys"]}
        r = requests.post(f"{API}/settings/keys/elevenlabs/validate", json={"key": "sk_invalid"}, timeout=40)
        assert r.status_code == 200
        assert r.json()["attempt"]["valid"] is False
        g = {k["provider"]: k for k in requests.get(f"{API}/settings/keys", timeout=30).json()["keys"]}
        assert g["elevenlabs"]["last4"] == before["elevenlabs"]["last4"]

    def test_unknown_provider_404(self):
        r = requests.put(f"{API}/settings/keys/openai", json={"key": "x"}, timeout=30)
        assert r.status_code == 404


# ---------- Deepgram WS proxy ----------
def test_ws_proxy_deepgram():
    import websockets

    async def run():
        msgs = []
        async with websockets.connect("ws://localhost:8001/api/stt/deepgram?keyterm=teste", open_timeout=15) as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), 15))
            assert first["type"] == "Ready", first
            chunk = b"\x00\x00" * 1600  # 100ms
            for _ in range(20):
                await ws.send(chunk)
                await asyncio.sleep(0.05)
            await ws.send(json.dumps({"type": "CloseStream"}))
            try:
                while True:
                    m = await asyncio.wait_for(ws.recv(), 10)
                    msgs.append(json.loads(m)["type"])
            except Exception:
                pass
        return msgs

    msgs = asyncio.run(run())
    print("ws msgs:", msgs)
    assert "Results" in msgs or "Metadata" in msgs


def test_ws_proxy_public_url():
    import websockets
    url = BASE_URL.replace("https://", "wss://") + "/api/stt/deepgram?keyterm=teste"

    async def run():
        async with websockets.connect(url, open_timeout=15) as ws:
            return json.loads(await asyncio.wait_for(ws.recv(), 15))["type"]

    assert asyncio.run(run()) == "Ready"


# ---------- Auto-marked non-script text ----------
class TestPaged:
    def test_paged_script(self):
        payload = json.load(open("/root/paged_script.json"))
        payload["title"] = "TEST_Paginado_r7"
        r = requests.post(f"{API}/scripts", json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        created.append(d["id"])
        lines = d["lines"]
        foreign = [ln["text"].strip() for ln in lines if ln["kind"] == "foreign"]
        print("foreign:", foreign)
        for t in ("- 1 -", "Pág. 2", "3", "* * *"):
            assert t in foreign
        assert foreign.count("O JARDIM — Acto I") == 3
        assert len(d["auto_marked"]) == 7
        chars = d.get("characters")
        names = sorted(c if isinstance(c, str) else c.get("name") for c in chars)
        assert names == ["ANA", "RUI"]
        for ln in lines:
            if ln.get("character") in ("ANA", "RUI"):
                assert ln["kind"] == "dialogue"
        r2 = requests.post(f"{API}/scripts/{d['id']}/auto-marked/dismiss", timeout=30)
        assert r2.status_code == 200
        g = requests.get(f"{API}/scripts/{d['id']}", timeout=30).json()
        assert g["auto_marked_dismissed"] is True


# ---------- Pronunciation ----------
class TestPronunciation:
    def test_get_estrangeiros(self):
        sid = find("TEST_Estrangeiros")
        d = requests.get(f"{API}/scripts/{sid}/pronunciation", timeout=30).json()
        items = d["items"]
        jg = [i for i in items if i["text"] == "Jean Genet"]
        assert jg and jg[0]["lang"] == "fr" and jg[0]["say"]
        s = requests.get(f"{API}/scripts/{sid}", timeout=30).json()
        assert "Jean Genet" in s["lines"][0].get("keyterms", [])

    def test_put_roundtrip(self):
        sid = find("TEST_Estrangeiros")
        orig = requests.get(f"{API}/scripts/{sid}/pronunciation", timeout=30).json()["items"]
        edited = [dict(i) for i in orig]
        edited[0]["say"] = "TESTSAY"
        r = requests.put(f"{API}/scripts/{sid}/pronunciation", json={"items": edited}, timeout=30)
        assert r.status_code == 200
        got = requests.get(f"{API}/scripts/{sid}/pronunciation", timeout=30).json()["items"]
        assert got[0]["say"] == "TESTSAY"
        requests.put(f"{API}/scripts/{sid}/pronunciation", json={"items": orig}, timeout=30)

    def test_detect_nova_iorque(self):
        text = ("ANA: Fui a Nova Iorque no verão passado.\n\nRUI: Eu prefiro dizer New York, como os americanos.\n\n"
                "ANA: Nova Iorque é bonita.\n\nRUI: New York nunca dorme.")
        r = requests.post(f"{API}/scripts", json={"title": "TEST_NovaIorque", "author": "t", "text": text}, timeout=60)
        sid = r.json()["id"]
        created.append(sid)
        d = requests.post(f"{API}/scripts/{sid}/pronunciation/detect", timeout=120)
        assert d.status_code == 200, d.text
        texts = [i["text"].lower() for i in d.json()["items"]]
        print("detected:", d.json()["items"])
        assert "new york" in texts
        assert not any("iorque" in t for t in texts)


# ---------- Matching ----------
class TestMatching:
    def m(self, a, b):
        from matching import local_match
        return local_match(a, b)

    def diffs(self, res):
        print(res)
        if isinstance(res, dict):
            return res.get("differences", res.get("diffs", []))
        if isinstance(res, tuple):
            for x in res:
                if isinstance(x, list):
                    return x
        return res

    def test_acronym(self):
        assert len(self.diffs(self.m("E depois ele arrota à mesa.", "E depois ele A RTP à mesa."))) == 0

    def test_prefix(self):
        assert len(self.diffs(self.m("Tu és um malandreco, sabias?", "Tu és um malandra, sabias?"))) == 0

    def test_real_sub(self):
        d = self.diffs(self.m("Nunca mais te vejo, casa.", "Nunca mais te vejo, rua."))
        assert len(d) == 1

    def test_long_omission(self):
        d = self.diffs(self.m("Hoje fui ao mercado comprar peixe fresco e depois voltei para casa a pé.", "Hoje fui ao mercado."))
        assert len(d) >= 1


# ---------- TTS ----------
def test_tts_foreign_edge():
    sid = find("TEST_Estrangeiros")
    r = requests.post(f"{API}/tts", json={"text": "Li o Jean Genet", "character": "RITA", "voice": "nova",
                                          "edge_voice": "pt-PT-RaquelNeural", "script_id": sid}, timeout=60)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mpeg")
    assert r.headers.get("x-tts-provider") == "edge"
    assert len(r.content) > 1000
