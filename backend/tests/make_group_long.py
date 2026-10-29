# Helper: create TEST_ script with 3 consecutive ANA lines + a >1000-char ANA line; prints ids
import json
from test_ensaio_phase3 import API, S

long = " ".join(["Esta é uma fala muito comprida que continua sem parar pela noite dentro."] * 16)
txt = f"""ANA: Primeira fala da Ana.
ANA: Segunda fala da Ana.
ANA: Terceira fala da Ana.
BRUNO: Muito bem, continua.
ANA: {long}
BRUNO: Chega por hoje.
ANA: Até amanhã.
"""
r = S.post(f"{API}/scripts", json={"title": "TEST_grupo_longo", "text": txt}, timeout=90).json()
s = S.post(f"{API}/sessions", json={"script_id": r["id"], "character": "ANA"}, timeout=30).json()
print(json.dumps({"script": r["id"], "session": s["id"], "longlen": len(long),
                  "lines": [(l["idx"], l["kind"], l["character"], len(l["text"])) for l in r["lines"]]}))
