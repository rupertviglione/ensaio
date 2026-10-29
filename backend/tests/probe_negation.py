# Probe: is a negation omission confirmed as real? (repeat 3x)
import sys, time
sys.path.insert(0, "/app/backend/tests")
from test_ensaio_phase2 import S, API, demo, session, turn

d = demo()
L = {ln["idx"]: ln["text"] for ln in d["lines"]}
for k in range(3):
    sid = session(d["id"], "MARTA")
    r = turn(sid, 5, L[5].replace("não sabia", "sabia")).json()
    r2 = turn(sid, 15, L[15].replace("ainda cá estás", "nunca cá estás")).json()
    f = S.post(f"{API}/sessions/{sid}/finish", timeout=120).json()
    print(k, "int5", r["turn"]["interrupted"], "int15", r2["turn"]["interrupted"], "REAL:", [(x["line_idx"], x["expected"], x["said"]) for x in f["summary"]["differences"]],
          "discarded", f["summary"]["stats"]["discarded"])
