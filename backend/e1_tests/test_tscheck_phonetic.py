from conftest import new_session
def test_near_homophones(c,sid):
    s=new_session(c,sid,"phon")
    for idx,said in [(2,"Ainda tás aqui? Pensei que já tivesses partido no comboio das seis"),
                     (9,None)]:
        if said is None:
            exp=c.get(f"/scripts/{sid}").json()["lines"][9]["text"]; said=exp.replace("à espera","há espera").replace(",","")
        t=c.post(f"/sessions/{s}/turn",json={"line_idx":idx,"said":said}).json()["turn"]
        assert t["differences"]==[] and t["severity"]=="none", t
