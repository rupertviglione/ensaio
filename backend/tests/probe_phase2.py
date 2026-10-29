# Exploratory probe (prints): meaning changes, omissions, homophones, block attribution
import json, time, sys
sys.path.insert(0, "/app/backend/tests")
from test_ensaio_phase2 import S, API, demo, session, turn, new_script

d = demo()
L = {ln["idx"]: ln["text"] for ln in d["lines"]}
sid = session(d["id"], "MARTA")
cases = [
    (5, L[5].replace("não sabia", "sabia")),  # negation removed
    (13, "Ouviste?"),  # omit sentence
    (15, "Vou. Mas só se me prometeres que, quando eu voltar, já cá não estás."),
    (10, "A tua avó era uma mulher sabia."),
    (7, "Hoje é dia de pedra."),
    (3, "Perdi-o ou melhor deixeio ir fiquei a vê lo afastar se e não me mexi"),
]
for i, said in cases:
    t0 = time.time()
    r = turn(sid, i, said).json()
    t = r["turn"]
    print(f"[{i}] {time.time()-t0:.1f}s adv={r['advance']} int={t['interrupted']} acc={t['accuracy']} sev={t['severity']} fb={t['feedback']!r}")
    print("    diffs:", [(x['expected'], x['said']) for x in t['differences']])
t0 = time.time()
f = S.post(f"{API}/sessions/{sid}/finish", timeout=120).json()
print(f"finish {time.time()-t0:.1f}s score={f['summary']['score']} stats={f['summary']['stats']}")
for x in f["summary"]["differences"]:
    print("  REAL:", x)
for t in f["turns"]:
    print("  turn", t["line_idx"], t["review"], t["final_accuracy"], [(x["expected"], x["said"], x["status"]) for x in t["differences"]])

# block with error in second line -> attribution
sc = new_script("TEST_P2 bloco2", "ANA: Olá Rui.\nRUI: Olá Ana. Tudo bem?\nANA: Tudo. Cheguei agora.\n(Pausa.)\nANA: E tu, o que fazes aqui?\nRUI: Espero o comboio.")
try:
    s2 = session(sc["id"], "ANA")
    r = turn(s2, 2, "Tudo. Cheguei agora. E tu, o que comes aqui?", [2, 4]).json()
    print("block diffs:", [(x["expected"], x["said"], x["line_idx"]) for x in r["turn"]["differences"]])
    r = turn(s2, 4, "Tudo.", [2, 4])
    print("line_idx not first:", r.status_code, r.text[:200])
    r = turn(s2, 2, "Tudo.", [2, 3])
    print("with stage dir:", r.status_code, r.text[:100])
    f = S.post(f"{API}/sessions/{s2}/finish", timeout=120).json()
    print("block summary diffs", f["summary"]["differences"], f["summary"]["stats"])
finally:
    S.delete(f"{API}/scripts/{sc['id']}")
