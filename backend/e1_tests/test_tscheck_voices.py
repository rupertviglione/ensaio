def test_voices_distinct_and_preview(c,sid):
    chars=c.get(f"/scripts/{sid}").json()["characters"]
    combos={(x["edge_voice"],x["edge_pitch"],x["edge_rate"]) for x in chars}
    assert all(x["edge_voice"].startswith("pt-PT") for x in chars) and len(combos)==len(chars)
    for x in chars:
        r=c.post("/tts",json={"text":"Olá","character":x["name"],"tts":"edge","edge_voice":x["edge_voice"],"edge_pitch":x["edge_pitch"],"edge_rate":x["edge_rate"]})
        assert r.status_code==200 and r.headers.get("x-tts-provider")=="edge" and len(r.content)>1000
