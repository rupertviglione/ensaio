import uuid, json, asyncio, websockets
def test_keys_masked(c):
    r=c.get("/settings/keys"); assert r.status_code==200
    ks=r.json()["keys"]; assert {k["provider"] for k in ks}>={"elevenlabs","deepgram","gemini"}
    for k in ks: assert "key" not in k and (k["last4"] is None or len(k["last4"])==4)
def test_unknown_provider_404(c):
    assert c.put("/settings/keys/nope",json={"key":"x"}).status_code==404
def test_page_numbers_auto_marked(c):
    t="CENA 1\n\nANA: Olá, como estás?\nRUI: Bem, obrigado.\n\n12\n\nANA: Ainda bem.\n\n13\n\nRUI: Até logo.\n"
    s=c.post("/scripts",json={"title":f"tscheck-nb-{uuid.uuid4().hex[:6]}","text":t}).json()
    by={l["text"]:l for l in s["lines"]}
    assert by["12"]["kind"]=="foreign" and by["13"]["kind"]=="foreign", s["lines"]
    assert all(l["kind"]=="dialogue" for l in s["lines"] if l["text"] in ("Olá, como estás?","Bem, obrigado.","Ainda bem.","Até logo."))
    assert s["auto_marked"], s.get("auto_marked")
def test_pronunciation_persist(c):
    s=c.post("/scripts",json={"title":f"tscheck-pr-{uuid.uuid4().hex[:6]}","text":"ANA: Fui ao shopping comprar um croissant.\nRUI: Que chic.\n"}).json()
    r=c.put(f"/scripts/{s['id']}/pronunciation",json={"items":[{"text":"croissant","lang":"fr","say":"cruassã"}]}); assert r.status_code==200,r.text
    g=c.get(f"/scripts/{s['id']}/pronunciation").json(); assert any(i["text"]=="croissant" for i in g["items"]), g
def test_deepgram_ws_ingress():
    import os
    async def go():
        async with websockets.connect("wss://falas-ator--6srpvdtu.preview.emergentagent.com/api/stt/deepgram",open_timeout=20) as ws:
            m=json.loads(await asyncio.wait_for(ws.recv(),20)); return m
    m=asyncio.run(go()); assert m["type"]=="Ready", m
def test_similar_dialogue_not_marked_header(c):
    t="".join(f"RUI: Fala do Rui numero {i}.\nANA: Fala da Ana numero {i}.\n" for i in range(4))+"PEDRO: Sim.\nANA: Vens?\nPEDRO: Sim.\nANA: Já?\nPEDRO: Sim.\n"
    s=c.post("/scripts",json={"title":f"tscheck-nbfp-{uuid.uuid4().hex[:6]}","text":t}).json()
    bad=[(l["idx"],l["text"]) for l in s["lines"] if l["kind"]=="foreign"]
    assert not bad, f"real dialogue auto-marked non-belonging: {bad}"
