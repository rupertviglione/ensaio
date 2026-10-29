import uuid
def mk(c):
    t="ANA: Ele arrota sempre ao jantar.\nRUI: És mesmo um malandreco, sabias bem disso.\nANA: Vou para casa agora mesmo.\nRUI: Ontem fui à praia com o meu irmão mais velho e comemos peixe grelhado no restaurante do porto antes de voltarmos.\n"
    s=c.post("/scripts",json={"title":f"tscheck-match-{uuid.uuid4().hex[:6]}","text":t}).json()
    d=[l for l in s["lines"] if l["kind"]=="dialogue"]; assert len(d)==4, s["lines"]
    ses=c.post("/sessions",json={"script_id":s["id"],"character":"ANA","instructions":"tscheck-match"}).json()["id"]
    return s,d,ses
def turn(c,ses,idx,said): r=c.post(f"/sessions/{ses}/turn",json={"line_idx":idx,"said":said}); assert r.status_code==200,r.text; return r.json()["turn"]
def exp(t): return [d["expected"].lower() for d in t["differences"]]
def test_homophones_accepted(c):
    s,d,ses=mk(c)
    t=turn(c,ses,d[0]["idx"],"Ele A RTP sempre ao jantar."); assert "arrota" not in " ".join(exp(t)), t
    t=turn(c,ses,d[1]["idx"],"És mesmo um malandra, sabias bem disso."); assert "malandreco" not in " ".join(exp(t)), t
def test_real_errors_flagged(c):
    s,d,ses=mk(c)
    t=turn(c,ses,d[2]["idx"],"Vou para rua agora mesmo."); assert any("casa" in e for e in exp(t)), t
    t=turn(c,ses,d[3]["idx"],"Ontem fui à praia."); assert t["differences"] and (t["accuracy"] or 0)<70, t
