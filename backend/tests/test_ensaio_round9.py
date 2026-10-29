# Round 9: mark_non_script false-positive probes + dry-run key validate + tts status
import os, uuid, pytest, requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
CREATED = []


def mk(text, title=None):
    r = requests.post(f"{API}/scripts", json={"title": title or f"TEST_r9-{uuid.uuid4().hex[:6]}", "text": text}, timeout=120)
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
    return [l for l in s["lines"] if l["kind"] == "foreign"]


# --- dialogue repeated, regularly spaced (gap 4) must not be marked
def test_maria_nao_regular():
    parts = []
    for i in range(4):
        parts += [f"ANA: Pergunta número {i} sobre a casa velha?", "MARIA: Não.", f"RUI: Comentário {i} sobre o tempo.", f"ANA: Mais uma frase diferente {i*7}."]
    s = mk("\n".join(parts))
    f = foreign(s)
    assert f == [], f
    assert sum(1 for l in s["lines"] if l.get("character") == "MARIA" and l["text"].strip() == "Não.") == 4


# --- PEDRO 'Sim.' x3 regularly spaced (gap 3)
def test_pedro_sim_regular():
    parts = []
    for i in range(3):
        parts += [f"ANA: Vens comigo à feira número {i}?", "PEDRO: Sim.", f"RUI: Eu também vou, na vez {i}."]
    s = mk("\n".join(parts))
    assert foreign(s) == [], foreign(s)


# --- repeated uppercase stage direction mid-scene, irregular, no page numbers
def test_uppercase_direction_irregular():
    parts = ["ANA: Olá.", "RUI: Bom dia.", "SILÊNCIO.", "ANA: Então?", "RUI: Nada.", "ANA: Pois.", "RUI: Sim?",
             "ANA: Vamos.", "RUI: Já.", "ANA: Espera.", "RUI: Diz.", "ANA: Ouve.", "SILÊNCIO.", "RUI: E agora?",
             "ANA: Agora nada.", "SILÊNCIO.", "RUI: Fim da conversa."]
    s = mk("\n".join(parts))
    assert foreign(s) == [], [l["text"] for l in foreign(s)]


# --- repeated footer near page numbers SHOULD be marked
def test_footer_near_page_numbers():
    parts = []
    for p in range(1, 4):
        parts += [f"ANA: Fala inicial da página {p}.", f"RUI: Resposta da página {p}.", f"ANA: Outra fala {p}.",
                  f"RUI: Mais texto {p}.", "", "Texto de João Silva", "", f"- {p} -", ""]
    s = mk("\n".join(parts))
    ft = [l["text"] for l in foreign(s)]
    assert sum(1 for t in ft if "João Silva" in t) == 3, ft
    assert all(l.get("character") for l in s["lines"] if l["kind"] == "dialogue")


# --- validate dry-run endpoint
def _keys():
    return {k["provider"]: (k["last4"], k["source"]) for k in requests.get(f"{API}/settings/keys", timeout=30).json()["keys"]}


@pytest.mark.parametrize("prov", ["elevenlabs", "deepgram", "gemini"])
def test_validate_invalid_not_saved(prov):
    before = _keys()
    r = requests.post(f"{API}/settings/keys/{prov}/validate", json={"key": "bogus_TEST_key_1234"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["provider"] == prov and d["saved"] is False
    assert d["attempt"]["valid"] is False and isinstance(d["attempt"]["message"], str)
    assert _keys() == before


def test_validate_unknown_404():
    assert requests.post(f"{API}/settings/keys/openai/validate", json={"key": "x"}, timeout=30).status_code == 404


def test_validate_empty_400():
    assert requests.post(f"{API}/settings/keys/deepgram/validate", json={"key": "   "}, timeout=30).status_code == 400


def test_tts_status_blocked_list():
    d = requests.get(f"{API}/tts/status", timeout=30).json()
    assert isinstance(d.get("eleven_blocked_voices"), list)
