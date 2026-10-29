# Helper: clone 'A Espera' into a TEST_ script (same lines) and create a MARTA session. Prints ids.
import sys, json, requests
from test_ensaio_phase3 import API, S

title = sys.argv[1] if len(sys.argv) > 1 else "TEST_Espera"
items = S.get(f"{API}/scripts", timeout=20).json()
d = next(s for s in items if s["title"] == "A Espera")
demo = S.get(f"{API}/scripts/{d['id']}", timeout=20).json()
txt = demo.get("raw_text") or "\n".join((f"{l['character']}: {l['text']}" if l["character"] else f"({l['text']})") for l in demo["lines"])
r = S.post(f"{API}/scripts", json={"title": title, "text": txt}, timeout=90).json()
s = S.post(f"{API}/sessions", json={"script_id": r["id"], "character": "MARTA"}, timeout=30).json()
print(json.dumps({"script": r["id"], "session": s["id"], "demo": d["id"],
                  "lines": [(l["idx"], l["kind"], l["character"], l["text"][:40]) for l in r["lines"]]}, ensure_ascii=False))
