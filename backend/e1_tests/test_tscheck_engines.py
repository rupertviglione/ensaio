import os
def test_engines(c):
    r=c.get("/stt/engines"); assert r.status_code==200; d=r.json()
    assert d["order"][0]=="deepgram" and d["deepgram"] and d["gemini"]
def test_tokens_not_raw_key(c):
    env=open("/app/backend/.env").read()
    keys={l.split("=",1)[0]:l.split("=",1)[1].strip().strip('"') for l in env.splitlines() if "=" in l}
    for ep,k in [("/stt/deepgram-token","DEEPGRAM_API_KEY"),("/stt/gemini-token","GEMINI_API_KEY")]:
        r=c.post(ep); assert r.status_code==200, r.text
        assert r.json().get("token") and keys[k] not in r.text
