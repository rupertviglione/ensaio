# Round 3: memory->script edits, focus sessions, script editor (PUT lines), rename character, voices
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

TEXT = """(Uma sala.)

ANA: Olá Pedro, chegaste cedo hoje.
PEDRO: Cheguei, o comboio veio mais rápido.
ANA: Hoje é dia de pedra.
PEDRO: Então vamos ensaiar já.
ANA: Vamos, mas primeiro um café."""


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def script(s):
    r = s.post(f"{API}/scripts", json={"title": "TEST_R3 api", "text": TEXT})
    assert r.status_code == 200, r.text
    d = r.json()
    yield d
    s.delete(f"{API}/scripts/{d['id']}")


def get(s, sid):
    r = s.get(f"{API}/scripts/{sid}")
    assert r.status_code == 200
    return r.json()


# --- (1) voices
@pytest.mark.skip(reason="obsolete since round4: premade ElevenLabs voices removed")
def test_voices_premade_fallback(s):
    d = s.get(f"{API}/voices").json()
    assert d["provider"] == "elevenlabs"
    assert d.get("pt_native") is False
    names = [v["name"] for v in d["elevenlabs"]]
    assert "Daniel" not in names and len(names) >= 10


# --- structure
def test_script_structure(script):
    ls = script["lines"]
    assert [l["kind"] for l in ls] == ["direction"] + ["dialogue"] * 5
    assert ls[3]["character"] == "ANA" and ls[3]["text"] == "Hoje é dia de pedra."
    assert all("edited_text" in l and l["edited_text"] is None for l in ls)
    # round4: characters default to OpenAI (no el_voice_id)


# --- (2) memory direct apply
def test_memory_direct_apply_and_delete(s, script):
    sid = script["id"]
    r = s.post(f"{API}/scripts/{sid}/memory", json={"text": "TEST direct", "line_idx": 2, "new_text": "Cheguei, o comboio veio cedo."})
    assert r.status_code == 200
    n = r.json()
    assert n["line_uid"] == script["lines"][2]["uid"] and n["new_text"] == "Cheguei, o comboio veio cedo."
    l2 = get(s, sid)["lines"][2]
    assert l2["edited_text"] == "Cheguei, o comboio veio cedo." and l2["edit_note_id"] == n["id"]
    assert l2["text"] == "Cheguei, o comboio veio mais rápido."
    s.delete(f"{API}/scripts/{sid}/memory/{n['id']}")
    l2 = get(s, sid)["lines"][2]
    assert l2["edited_text"] is None and l2["edit_note_id"] is None


# --- (2) memory AI linking
def test_memory_ai_link(s, script):
    sid = script["id"]
    t0 = time.time()
    r = s.post(f"{API}/scripts/{sid}/memory",
               json={"text": 'Na fala da ANA, agora digo "Hoje é mesmo dia de pedra" em vez de "Hoje é dia de pedra"'})
    dt = time.time() - t0
    print(f"AI link took {dt:.2f}s")
    assert r.status_code == 200
    n = r.json()
    assert n["line_uid"] == script["lines"][3]["uid"], n
    assert "mesmo" in n["new_text"].lower()
    l3 = get(s, sid)["lines"][3]
    assert l3["edited_text"] == n["new_text"]


def test_memory_ai_non_edit_note(s, script):
    r = s.post(f"{API}/scripts/{script['id']}/memory", json={"text": "TEST lembrar de respirar fundo antes de entrar em cena"})
    assert r.status_code == 200
    n = r.json()
    assert n["line_uid"] is None and n["new_text"] is None
    s.delete(f"{API}/scripts/{script['id']}/memory/{n['id']}")


# --- (2) turn evaluation uses edited text
def test_turn_uses_edited_text(s, script):
    sid = script["id"]
    l3 = get(s, sid)["lines"][3]
    assert l3["edited_text"], "depends on test_memory_ai_link"
    sess = s.post(f"{API}/sessions", json={"script_id": sid, "character": "ANA"}).json()
    t0 = time.time()
    r = s.post(f"{API}/sessions/{sess['id']}/turn", json={"line_idx": 3, "said": l3["edited_text"], "mode": "escrito"})
    dt = time.time() - t0
    print(f"edited turn {dt:.2f}s")
    d = r.json()
    assert r.status_code == 200
    assert d["advance"] is True
    assert d["turn"]["expected"] == l3["edited_text"]
    assert dt < 1.5


# --- (3) focus session
def test_focus_session_persisted(s, script):
    sess = s.post(f"{API}/sessions", json={"script_id": script["id"], "character": "ANA", "start_idx": 3, "focus_idxs": [3, 5]})
    assert sess.status_code == 200
    d = s.get(f"{API}/sessions/{sess.json()['id']}").json()
    assert d["focus_idxs"] == [3, 5] and d["start_idx"] == 3


# --- (4) PUT lines editor
def test_update_lines(s, script):
    sid = script["id"]
    cur = get(s, sid)
    ana_before = next(c for c in cur["characters"] if c["name"] == "ANA")
    ls = [{"uid": l["uid"], "character": l["character"], "text": l["text"], "kind": l["kind"]} for l in cur["lines"]]
    ls[1]["text"] = "Olá Pedro, chegaste tão cedo."
    ls[4]["character"] = "rui"  # new character, lower case -> upper
    ls[2] = {"uid": ls[2]["uid"], "character": None, "text": "(Pedro senta-se.)", "kind": "direction"}
    del ls[5]
    ls.append({"character": "ANA", "text": "TEST nova fala no fim.", "kind": "dialogue"})
    ls.append({"character": "ANA", "text": "   ", "kind": "dialogue"})  # empty -> dropped
    r = s.put(f"{API}/scripts/{sid}/lines", json={"lines": ls})
    assert r.status_code == 200, r.text
    d = r.json()
    out = d["lines"]
    assert [l["idx"] for l in out] == list(range(len(out))) and len(out) == 6
    assert out[1]["text"] == "Olá Pedro, chegaste tão cedo."
    assert out[2]["kind"] == "direction" and out[2]["character"] is None
    assert out[4]["character"] == "RUI"
    assert out[5]["text"] == "TEST nova fala no fim." and out[5]["uid"]
    names = [c["name"] for c in d["characters"]]
    assert names == ["ANA", "RUI"], names  # PEDRO has no lines anymore
    ana = next(c for c in d["characters"] if c["name"] == "ANA")
    assert ana["el_voice_id"] == ana_before["el_voice_id"] and ana["voice"] == ana_before["voice"]
    # round4: no default ElevenLabs voice anymore
    # edited line 3 (ANA) memory kept
    assert out[3]["edited_text"]
    g = get(s, sid)
    assert [l["text"] for l in g["lines"]] == [l["text"] for l in out]


def test_update_lines_prunes_memory(s, script):
    sid = script["id"]
    cur = get(s, sid)
    ls = [{"uid": l["uid"], "character": l["character"], "text": l["text"], "kind": l["kind"]} for l in cur["lines"] if l["idx"] != 3]
    r = s.put(f"{API}/scripts/{sid}/lines", json={"lines": ls})
    assert r.status_code == 200
    assert all(m["line_uid"] is None for m in r.json()["memory"])


def test_update_lines_no_dialogue(s, script):
    r = s.put(f"{API}/scripts/{script['id']}/lines", json={"lines": [{"text": "(só rubrica)", "kind": "direction"}]})
    assert r.status_code == 400


# --- (4) rename character
def test_rename_and_merge(s, script):
    sid = script["id"]
    r = s.post(f"{API}/scripts/{sid}/rename-character", json={"old": "RUI", "new": "Rui Costa"})
    assert r.status_code == 200
    d = r.json()
    assert "RUI COSTA" in [c["name"] for c in d["characters"]] and "RUI" not in [c["name"] for c in d["characters"]]
    assert any(l["character"] == "RUI COSTA" for l in d["lines"])
    r = s.post(f"{API}/scripts/{sid}/rename-character", json={"old": "RUI COSTA", "new": "ana"})
    d = r.json()
    assert [c["name"] for c in d["characters"]] == ["ANA"]
    assert all(l["character"] in ("ANA", None) for l in d["lines"])
    assert [c["name"] for c in get(s, sid)["characters"]] == ["ANA"]


def test_rename_invalid(s, script):
    r = s.post(f"{API}/scripts/{script['id']}/rename-character", json={"old": "NINGUEM", "new": "X"})
    assert r.status_code == 400
    r = s.post(f"{API}/scripts/{script['id']}/rename-character", json={"old": "ANA", "new": "  "})
    assert r.status_code == 400


def test_rename_same_name_keeps_character(s, script):
    """Renaming ANA -> 'ana' (same after upper) must not delete the character."""
    r = s.post(f"{API}/scripts/{script['id']}/rename-character", json={"old": "ANA", "new": "ana"})
    assert r.status_code in (200, 400)
    assert "ANA" in [c["name"] for c in get(s, script["id"])["characters"]]
