import uuid
TXT="""ANA: Bom dia, Rui.
RUI: Bom dia. Estás atrasada.
(Pausa.)
RUI: O comboio já partiu há muito tempo.
ANA: Eu sei, eu sei."""
def test_block_judged_once(c):
    r=c.post("/scripts",json={"title":f"tscheck-blk-{uuid.uuid4().hex[:6]}","text":TXT}); assert r.status_code==200, r.text
    sc=r.json(); lines=sc["lines"]
    rui=[l["idx"] for l in lines if l["character"]=="RUI"]
    assert len(rui)==2, lines
    s=c.post("/sessions",json={"script_id":sc["id"],"character":"RUI","instructions":"tscheck-blk"}).json()["id"]
    said="Bom dia estás atrasada o comboio já partiu há muito tempo"
    r=c.post(f"/sessions/{s}/turn",json={"line_idx":rui[0],"line_idxs":rui,"said":said}); assert r.status_code==200, r.text
    t=r.json()["turn"]; assert t["line_idxs"]==rui and t["differences"]==[], t
    assert len(c.get(f"/sessions/{s}").json()["turns"])==1
