# Round 10: adversarial probes for mark_non_script (dialogue must never be auto-marked foreign without page-break evidence)
import os, uuid, pytest, requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
CREATED = []


def mk(text, title=None):
    r = requests.post(f"{API}/scripts", json={"title": title or f"TEST_r10-{uuid.uuid4().hex[:6]}", "text": text}, timeout=120)
    assert r.status_code in (200, 201), r.text
    s = r.json()
    CREATED.append(s["id"])
    return s


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for i in CREATED:
        requests.delete(f"{API}/scripts/{i}", timeout=30)


def foreign(s):
    return [(l["text"], l.get("character")) for l in s["lines"] if l["kind"] == "foreign"]


def pad(parts):
    # non-repeating padding at start/end so nothing sits at document edges
    return ["ANA: Abertura única da cena.", "RUI: Resposta única de abertura."] + parts + ["ANA: Penúltima fala única.", "RUI: Última fala única."]


# --- shouted ALL-CAPS dialogue repeated regularly, no page numbers
def test_shouted_caps_regular():
    parts = []
    for i in range(3):
        parts += [f"RUI: Vais sair outra vez, pela vez {i}?", "ANA: NÃO!", f"RUI: Está bem, fica {i}."]
    s = mk("\n".join(pad(parts)))
    assert foreign(s) == [], foreign(s)
    assert sum(1 for l in s["lines"] if l.get("character") == "ANA" and l["text"].strip() == "NÃO!") == 3


# --- dialogue containing 'Acto' repeated x3 mid-scene
def test_acto_dialogue_repeated():
    parts = []
    for i in range(3):
        parts += [f"ANA: Quando entras tu, ensaio {i}?", "RUI: Só no Acto dois.", f"ANA: Percebido, nota {i}."]
    s = mk("\n".join(pad(parts)))
    assert foreign(s) == [], foreign(s)
    assert sum(1 for l in s["lines"] if l.get("character") == "RUI" and "Acto" in l["text"]) == 3


# --- dialogue containing em dash / title repeated x3 mid-scene
def test_title_in_dialogue_repeated():
    parts = []
    for i in range(3):
        parts += [f"ANA: Que peça fazemos, {i}?", "RUI: O Jardim — claro.", f"ANA: Ok {i}."]
    s = mk("\n".join(pad(parts)), title="O Jardim")
    assert foreign(s) == [], foreign(s)


# --- caps dialogue x3 where 2 occurrences are at document edges (near_break i<=1 / i>=len-2)
def test_caps_dialogue_at_edges():
    parts = ["ANA: NÃO!", "RUI: Calma, primeira.", "ANA: Ouve.", "RUI: Diz.", "ANA: NÃO!", "RUI: Pronto.", "ANA: Vá.", "RUI: Fim.", "ANA: NÃO!"]
    s = mk("\n".join(parts))
    assert foreign(s) == [], foreign(s)


# --- digit-only differences in dialogue never folded
def test_digit_variants_dialogue():
    parts = []
    for i in range(4):
        parts += [f"ANA: ACTO {i+1}!", f"RUI: Frase diferente {i*3}.", f"ANA: Mais uma {i}."]
    s = mk("\n".join(pad(parts)))
    assert foreign(s) == [], foreign(s)


# --- regression: real running header + page numbers still marked
def test_real_header_still_marked():
    parts = []
    for p in range(1, 4):
        parts += ["O JARDIM — Acto I", "", f"ANA: Fala {p} da página.", f"RUI: Resposta {p}.", f"ANA: Outra {p}.", "", f"- {p} -", ""]
    s = mk("\n".join(parts), title="O Jardim")
    f = [t for t, _ in foreign(s)]
    assert sum(1 for t in f if "JARDIM" in t) == 3, f
    assert sum(1 for t in f if t.strip().startswith("-")) == 3, f
    assert not any(l["kind"] == "foreign" for l in s["lines"] if l.get("character") in ("ANA", "RUI"))


# --- uppercase stage direction regularly spaced mid-scene (informational: direction path allows _regular)
def test_caps_direction_regular_probe():
    parts = []
    for i in range(3):
        parts += [f"ANA: Fala {i} da Ana.", "PAUSA.", f"RUI: Fala {i} do Rui."]
    s = mk("\n".join(pad(parts)))
    print("caps direction regular foreign:", foreign(s))
    assert foreign(s) == [], foreign(s)
