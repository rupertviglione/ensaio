import httpx, pytest
API="http://localhost:8001/api"
@pytest.fixture(scope="session")
def c():
    with httpx.Client(base_url=API, timeout=90) as cl: yield cl
@pytest.fixture(scope="session")
def sid(c):
    return next(s["id"] for s in c.get("/scripts").json() if s["title"]=="A Espera")
def new_session(c, sid, tag):
    r=c.post("/sessions", json={"script_id":sid,"character":"JOÃO","instructions":f"tscheck-{tag}"}); assert r.status_code==200; return r.json()["id"]
