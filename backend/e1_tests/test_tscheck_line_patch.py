import uuid
TXT="""ANA: Bom dia, Rui.
RUI: Bom dia. Estás atrasada.
RUI: O comboio já partiu.
ANA: Eu sei."""
def _mk(c):
    r=c.post("/scripts",json={"title":f"tscheck-patch-{uuid.uuid4().hex[:6]}","text":TXT}); assert r.status_code==200, r.text
    return r.json()
def test_patch_text_character_cut_persist(c):
    sc=_mk(c); l=sc["lines"]
    r=c.patch(f"/scripts/{sc['id']}/lines/{l[1]['uid']}",json={"text":"tscheck novo texto"}); assert r.status_code==200, r.text
    r=c.patch(f"/scripts/{sc['id']}/lines/{l[2]['uid']}",json={"character":"ANA"}); assert r.status_code==200, r.text
    r=c.patch(f"/scripts/{sc['id']}/lines/{l[3]['uid']}",json={"kind":"cut"}); assert r.status_code==200, r.text
    g=c.get(f"/scripts/{sc['id']}").json()["lines"]
    assert (g[1].get("edited_text") or g[1]["text"])=="tscheck novo texto", g[1]
    assert g[2]["character"]=="ANA" and g[3]["kind"]=="cut", g
def test_patch_rejects_bad(c):
    sc=_mk(c)
    assert c.patch(f"/scripts/{sc['id']}/lines/{sc['lines'][0]['uid']}",json={"kind":"bogus"}).status_code==422
    assert c.patch(f"/scripts/{sc['id']}/lines/nouid",json={"text":"x"}).status_code in (404,422,400)
def test_bulk_kinds_via_put(c):
    sc=_mk(c); ls=[{k:l.get(k) for k in ("uid","character","text","kind")} for l in sc["lines"]]
    ls.append({"uid":None,"character":"ANA","text":"Fim.","kind":"dialogue"})
    for l in ls[:3]: l["kind"]="direction"
    ls[3]["kind"]="foreign"
    r=c.put(f"/scripts/{sc['id']}/lines",json={"lines":ls}); assert r.status_code==200, r.text
    g=c.get(f"/scripts/{sc['id']}").json()["lines"]
    assert [x["kind"] for x in g]==["direction"]*3+["foreign","dialogue"], g
