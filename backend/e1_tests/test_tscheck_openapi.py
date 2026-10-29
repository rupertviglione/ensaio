def test_openapi(c): assert c.get("/openapi.json").status_code==200
