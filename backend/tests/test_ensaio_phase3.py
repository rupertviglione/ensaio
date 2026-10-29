# Phase 3 (F-17..F-23) tests: PATCH /scripts/{id}/lines/{uid}, kinds foreign/cut via PUT, characters persistence
import os
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
S = requests.Session()

TEXT = """MARTA: Olá, estás aí?
JOÃO: Estou sim, à tua espera.
(Pausa longa.)
MARTA: Então vamos embora.
PEDRO: Esperem por mim!
JOÃO: Despacha-te, Pedro.
"""


@pytest.fixture(scope="module")
def sc():
    r = S.post(f"{API}/scripts", json={"title": "TEST_phase3_patch", "text": TEXT}, timeout=60)
    assert r.status_code in (200, 201), r.text
    s = r.json()
    yield s
    S.delete(f"{API}/scripts/{s['id']}", timeout=20)


def get(sid):
    return S.get(f"{API}/scripts/{sid}", timeout=20).json()


def patch(sid, uid, body):
    return S.patch(f"{API}/scripts/{sid}/lines/{uid}", json=body, timeout=20)


def line(s, idx):
    return next(l for l in s["lines"] if l["idx"] == idx)


# Line edit: text / character / cut / restore / foreign / validation
class TestPatchLine:
    def test_structure(self, sc):
        kinds = [l["kind"] for l in sc["lines"]]
        assert "direction" in kinds and kinds.count("dialogue") >= 5
        assert {c["name"] for c in sc["characters"]} >= {"MARTA", "JOÃO", "PEDRO"}

    def test_text_update_persists(self, sc):
        ln = next(l for l in sc["lines"] if l["character"] == "MARTA")
        r = patch(sc["id"], ln["uid"], {"text": "  Olá, ainda estás aí?  "})
        assert r.status_code == 200, r.text
        assert line(r.json(), ln["idx"])["text"] == "Olá, ainda estás aí?"
        assert line(get(sc["id"]), ln["idx"])["text"] == "Olá, ainda estás aí?"

    def test_character_reassign(self, sc):
        ln = next(l for l in sc["lines"] if l["character"] == "JOÃO")
        r = patch(sc["id"], ln["uid"], {"character": "MARTA"})
        assert r.status_code == 200
        g = line(get(sc["id"]), ln["idx"])
        assert g["character"] == "MARTA" and g["kind"] == "dialogue"
        patch(sc["id"], ln["uid"], {"character": "JOÃO"})
        assert line(get(sc["id"]), ln["idx"])["character"] == "JOÃO"

    def test_direction_with_character_becomes_dialogue(self, sc):
        d = next(l for l in get(sc["id"])["lines"] if l["kind"] == "direction")
        r = patch(sc["id"], d["uid"], {"character": "PEDRO"})
        assert r.status_code == 200
        g = line(get(sc["id"]), d["idx"])
        assert g["kind"] == "dialogue" and g["character"] == "PEDRO"
        r = patch(sc["id"], d["uid"], {"kind": "direction"})
        g = line(r.json(), d["idx"])
        assert g["kind"] == "direction" and g["character"] is None

    def test_cut_keeps_character_and_restore(self, sc):
        ln = next(l for l in sc["lines"] if l["character"] == "MARTA")
        r = patch(sc["id"], ln["uid"], {"kind": "cut"})
        assert r.status_code == 200
        g = line(get(sc["id"]), ln["idx"])
        assert g["kind"] == "cut" and g["character"] == "MARTA"
        r = patch(sc["id"], ln["uid"], {"kind": "dialogue"})
        g = line(get(sc["id"]), ln["idx"])
        assert g["kind"] == "dialogue" and g["character"] == "MARTA"

    def test_characters_keep_cut_only(self, sc):
        p = next(l for l in get(sc["id"])["lines"] if l["character"] == "PEDRO" and l["kind"] == "dialogue")
        # PEDRO has only this one line besides the temporary direction above (restored)
        others = [l for l in get(sc["id"])["lines"] if l["character"] == "PEDRO" and l["uid"] != p["uid"]]
        assert not others
        r = patch(sc["id"], p["uid"], {"kind": "cut"})
        assert r.status_code == 200
        assert "PEDRO" in [c["name"] for c in get(sc["id"])["characters"]]
        patch(sc["id"], p["uid"], {"kind": "dialogue"})

    def test_foreign_clears_character(self, sc):
        ln = [l for l in sc["lines"] if l["character"] == "JOÃO"][-1]
        r = patch(sc["id"], ln["uid"], {"kind": "foreign"})
        assert r.status_code == 200
        g = line(get(sc["id"]), ln["idx"])
        assert g["kind"] == "foreign" and g["character"] is None
        r = patch(sc["id"], ln["uid"], {"character": "JOÃO"})
        g = line(get(sc["id"]), ln["idx"])
        assert g["kind"] == "dialogue" and g["character"] == "JOÃO"

    def test_empty_text_400(self, sc):
        ln = sc["lines"][0]
        r = patch(sc["id"], ln["uid"], {"text": "   "})
        assert r.status_code == 400
        assert line(get(sc["id"]), ln["idx"])["text"].strip()

    def test_unknown_uid_404(self, sc):
        assert patch(sc["id"], "nope-uid-xyz", {"text": "x"}).status_code == 404

    def test_invalid_kind_422(self, sc):
        assert patch(sc["id"], sc["lines"][0]["uid"], {"kind": "bogus"}).status_code == 422

    def test_memory_link_cleared_on_text_edit(self, sc):
        s = get(sc["id"])
        ln = next(l for l in s["lines"] if l["character"] == "JOÃO")
        r = S.post(f"{API}/scripts/{sc['id']}/memory", json={"text": "TEST nota", "line_idx": ln["idx"], "new_text": "Texto acordado pela nota."}, timeout=60)
        assert r.status_code == 200, r.text
        assert line(get(sc["id"]), ln["idx"]).get("edited_text") == "Texto acordado pela nota."
        r = patch(sc["id"], ln["uid"], {"text": "Texto novo da edição."})
        assert r.status_code == 200
        g = line(get(sc["id"]), ln["idx"])
        assert g["text"] == "Texto novo da edição." and not g.get("edited_text")


# Guião editor bulk save: PUT accepts foreign and cut
class TestPutKinds:
    def test_put_foreign_cut(self, sc):
        s = get(sc["id"])
        body = [{"uid": l["uid"], "character": l["character"], "text": l["text"], "kind": l["kind"]} for l in s["lines"]]
        body[0]["kind"] = "foreign"
        body[1]["kind"] = "cut"
        r = S.put(f"{API}/scripts/{sc['id']}/lines", json={"lines": body}, timeout=30)
        assert r.status_code == 200, r.text
        g = get(sc["id"])
        assert g["lines"][0]["kind"] == "foreign" and g["lines"][0]["character"] is None
        assert g["lines"][1]["kind"] == "cut" and g["lines"][1]["character"] == "JOÃO"
        assert [l["uid"] for l in g["lines"]] == [l["uid"] for l in s["lines"]]

    def test_put_no_dialogue_400(self, sc):
        s = get(sc["id"])
        body = [{"uid": l["uid"], "character": l["character"], "text": l["text"], "kind": "cut"} for l in s["lines"]]
        r = S.put(f"{API}/scripts/{sc['id']}/lines", json={"lines": body}, timeout=30)
        assert r.status_code == 400
