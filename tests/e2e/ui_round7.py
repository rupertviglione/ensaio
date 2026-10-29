# Round 7 UI checks: Definições, Pronúncia, auto-marked note/REPOR, Vozes engine select
import asyncio
import json

import httpx
from playwright.async_api import async_playwright

URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
API = URL + "/api"
SS = "/app/tests/e2e/shots"
R = []


def ok(name, cond, extra=""):
    R.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name, extra)


async def main():
    import os
    os.makedirs(SS, exist_ok=True)
    c = httpx.Client(timeout=60)
    scripts = c.get(f"{API}/scripts").json()
    est = next(s["id"] for s in scripts if s["title"] == "TEST_Estrangeiros")
    orig_pron = c.get(f"{API}/scripts/{est}/pronunciation").json()["items"]
    paged = json.load(open("/root/paged_script.json"))
    paged["title"] = "TEST_Paginado_ui7"
    pid = c.post(f"{API}/scripts", json=paged).json()["id"]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/root/bin/chromium", args=["--no-sandbox"])
        page = await b.new_page(viewport={"width": 1920, "height": 1080})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        try:
            # ---- Settings ----
            await page.goto(URL)
            await page.click('[data-testid="nav-settings"]')
            await page.wait_for_url("**/definicoes")
            await page.wait_for_selector('[data-testid="key-card-gemini"]')
            for pv in ("elevenlabs", "deepgram", "gemini"):
                ok(f"key-card-{pv}", await page.is_visible(f'[data-testid="key-card-{pv}"]'),
                   await page.text_content(f'[data-testid="key-last4-{pv}"]'))
            ok("tts-primary edge", "EDGE" in (await page.text_content('[data-testid="tts-primary"]')))
            for pv in ("deepgram", "gemini"):
                await page.click(f'[data-testid="key-check-btn-{pv}"]')
                await page.wait_for_selector(f'[data-testid="key-valid-{pv}"]', timeout=20000)
                await page.wait_for_timeout(1500)
                t = await page.text_content(f'[data-testid="key-valid-{pv}"]')
                ok(f"check {pv} valid", "válida" in t and "inválida" not in t, t)
            ok("deepgram credits shown", await page.locator('[data-testid="key-credits-deepgram"]').count() > 0)
            await page.fill('[data-testid="key-input-deepgram"]', "abc123")
            await page.click('[data-testid="key-save-btn-deepgram"]')
            await page.wait_for_timeout(4000)
            toast = await page.locator("[data-sonner-toast]").all_text_contents()
            ok("invalid key error toast", any("inválida" in t for t in toast), toast)
            ok("old key kept", (await page.text_content('[data-testid="key-last4-deepgram"]')) == "d7ba")
            st = await page.text_content('[data-testid="key-status-deepgram"]')
            print("deepgram status after invalid save:", st)
            ok("working key status still valid after invalid attempt", "inválida" not in st)
            await page.screenshot(path=f"{SS}/settings.jpg", quality=40, type="jpeg")
            await page.click('[data-testid="key-check-btn-deepgram"]')
            await page.wait_for_timeout(3000)

            # ---- Pronunciation ----
            await page.goto(f"{URL}/texto/{est}")
            await page.click('[data-testid="tab-pronunciation"]')
            await page.wait_for_selector('[data-testid="pron-row-0"]', timeout=15000)
            n = await page.locator('[data-testid^="pron-row-"]').count()
            ok("pron rows", n >= 1, n)
            ok("pron Jean Genet", any(
                [await page.input_value(f'[data-testid="pron-text-{i}"]') == "Jean Genet" for i in range(n)]))
            await page.click('[data-testid="pron-add-btn"]')
            await page.fill(f'[data-testid="pron-text-{n}"]', "Pas de deux")
            await page.select_option(f'[data-testid="pron-lang-{n}"]', "fr")
            await page.fill(f'[data-testid="pron-say-{n}"]', "Pá de dê")
            await page.fill(f'[data-testid="pron-variants-{n}"]', "pa de de, pá de dê")
            await page.click('[data-testid="pron-save-btn"]')
            await page.wait_for_timeout(2500)
            await page.reload()
            await page.click('[data-testid="tab-pronunciation"]')
            await page.wait_for_selector('[data-testid="pron-row-0"]', timeout=15000)
            n2 = await page.locator('[data-testid^="pron-row-"]').count()
            vals = [await page.input_value(f'[data-testid="pron-text-{i}"]') for i in range(n2)]
            ok("pron add persisted after reload?", "Pas de deux" in vals, vals)
            await page.screenshot(path=f"{SS}/pron.jpg", quality=40, type="jpeg")
            await page.click('[data-testid="pron-detect-btn"]')
            try:
                await page.wait_for_function("() => !document.querySelector('[data-testid=pron-detect-btn]').disabled", timeout=90000)
                await page.wait_for_timeout(500)
                toast = await page.locator("[data-sonner-toast]").all_text_contents()
                ok("detect done", any("detectadas" in t for t in toast), toast)
            except Exception as e:
                ok("detect done", False, str(e)[:100])

            # ---- Vozes ----
            await page.click('[data-testid="tab-voices"]')
            await page.wait_for_selector('[data-testid^="character-engine-select-"]', timeout=15000)
            t = await page.locator('[data-testid^="character-engine-select-"]').first.text_content()
            ok("engine select default Automático", "Automático" in t, t)
            await page.locator('[data-testid^="character-engine-select-"]').first.click()
            await page.wait_for_timeout(300)
            opts = await page.get_by_role("option").all_text_contents()
            ok("engine options include Automático", any("Automático (principal da app)" in o for o in opts), opts)
            await page.keyboard.press("Escape")

            # ---- Guião auto-marked ----
            await page.goto(f"{URL}/texto/{pid}")
            await page.wait_for_selector('[data-testid="auto-marked-note"]', timeout=15000)
            ok("auto-marked count 7", (await page.text_content('[data-testid="auto-marked-count"]')) == "7")
            await page.click('[data-testid="auto-marked-review-btn"]')
            await page.wait_for_timeout(800)
            btns = page.locator('[data-testid^="revert-foreign-btn-"]')
            ok("revert buttons", await btns.count() == 7, await btns.count())
            await page.screenshot(path=f"{SS}/guiao.jpg", quality=40, type="jpeg")
            tid = await btns.nth(1).get_attribute("data-testid")
            idx = int(tid.split("-")[-1])
            await btns.nth(1).click()
            await page.wait_for_timeout(2000)
            s = c.get(f"{API}/scripts/{pid}").json()
            ln = next(l for l in s["lines"] if l["idx"] == idx)
            ok("REPOR → direction", ln["kind"] == "direction", f"{ln['text']} {ln['kind']}")
            ok("count now 6", (await page.text_content('[data-testid="auto-marked-count"]')) == "6")
            await page.click('[data-testid="auto-marked-dismiss-btn"]')
            await page.wait_for_timeout(1500)
            ok("note hidden", await page.locator('[data-testid="auto-marked-note"]').count() == 0)
            await page.reload()
            await page.wait_for_selector('[data-testid="script-view"]', timeout=15000)
            await page.wait_for_timeout(1000)
            ok("note hidden after reload", await page.locator('[data-testid="auto-marked-note"]').count() == 0)
        except Exception as e:
            ok("exception", False, str(e)[:300])
            await page.screenshot(path=f"{SS}/err.jpg", quality=40, type="jpeg")
        print("page errors:", errs)
        await b.close()
    c.put(f"{API}/scripts/{est}/pronunciation", json={"items": orig_pron})
    c.delete(f"{API}/scripts/{pid}")
    print(f"{sum(x for _, x in R)}/{len(R)} passed")


asyncio.run(main())
