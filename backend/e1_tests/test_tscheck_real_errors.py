from conftest import new_session
def test_correct_session_zero(c,sid):
    s=new_session(c,sid,"ok")
    c.post(f"/sessions/{s}/turn",json={"line_idx":2,"said":"ainda tás aqui pensei que já tivesses partido no comboio das seis"})
    c.post(f"/sessions/{s}/turn",json={"line_idx":4,"said":"porquê"})
    r=c.post(f"/sessions/{s}/finish"); assert r.status_code==200
    assert all(t["differences"]==[] for t in r.json()["turns"]), r.text[:800]
def test_negation_and_skip_flagged(c,sid):
    s=new_session(c,sid,"err")
    t=c.post(f"/sessions/{s}/turn",json={"line_idx":11,"said":"Era teimosa. Mas também era sábia. Uma coisa sempre impede a outra."}).json()["turn"]
    assert t["differences"], t
    t2=c.post(f"/sessions/{s}/turn",json={"line_idx":11,"said":"Era teimosa. Uma coisa não impede a outra."}).json()["turn"]
    assert t2["differences"], t2
