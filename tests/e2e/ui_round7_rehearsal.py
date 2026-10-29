# Round 7 rehearsal UI: Deepgram badge, teleprompter for long lines, layout at 1920x800, phase-3 regressions
import asyncio
import httpx
from playwright.async_api import async_playwright

URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
API = URL + "/api"
SS = "/app/tests/e2e/shots"
R = []
LONG = ("Eu lembro-me bem daquela manhã em que tudo começou, quando a chuva caía sobre os telhados da cidade velha. "
        "A minha mãe estava na cozinha a preparar o café e o meu pai lia o jornal em silêncio, como sempre fazia. "
        "Ninguém imaginava que, poucas horas depois, a nossa vida iria mudar para sempre de uma forma tão brusca. "
        "Quando o telefone tocou, foi a minha irmã que atendeu, e eu vi a cara dela ficar branca como a cal da parede. "
        "Depois disso, lembro-me apenas do silêncio, um silêncio tão pesado que parecia encher a casa inteira.")


def ok(name, cond, extra=""):
    R.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name, extra)


async def main():
    c = httpx.Client(timeout=60)
    text = f"PEDRO: Então, conta-me.\n\nLUÍSA: {LONG}\n\nPEDRO: E depois?\n\nLUÍSA: Depois fui embora.\n\nPEDRO: Fizeste bem.\n\nLUÍSA: Talvez."
    s = c.post(f"{API}/scripts", json={"title": "TEST_Teleprompter_r7", "author": "t", "text": text}).json()
    sid = s["id"]
    print("chars:", [ch["name"] for ch in s["characters"]], "len long:", len(LONG))
    long_idx = next(l["idx"] for l in s["lines"] if l["character"] == "LUÍSA")
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/root/bin/chromium", args=[
            "--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            "--autoplay-policy=no-user-gesture-required"])
        ctx = await b.new_context(permissions=["microphone"], viewport={"width": 1920, "height": 800})
        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        try:
            sess = c.post(f"{API}/sessions", json={"script_id": sid, "character": "LUÍSA", "start_idx": long_idx}).json()
            await page.goto(f"{URL}/ensaio/{sess['id']}")
            await page.wait_for_selector('[data-testid="play-btn"]', timeout=20000)
            await page.click('[data-testid="play-btn"]')
            badge = ""
            for _ in range(30):
                await asyncio.sleep(0.5)
                badge = await page.get_by_test_id("stt-engine-name").inner_text()
                if "Deepgram" in badge:
                    break
            ok("badge Escuta: Deepgram", "escuta: deepgram" in badge.lower(), badge)
            w = page.locator('[data-testid="current-line-window"]')
            await w.wait_for(timeout=10000)
            mode = await w.get_attribute("data-mode")
            box = await w.bounding_box()
            ok("teleprompter mode", mode == "teleprompter", f"mode={mode} sentences={await w.get_attribute('data-sentences')}")
            ok("fixed height ~168", box and 140 <= box["height"] <= 200, box)
            for t in ("rehearsal-status", "rehearsal-controls"):
                bb = await page.locator(f'[data-testid="{t}"]').bounding_box()
                ok(f"{t} in viewport", bb and bb["y"] >= 0 and bb["y"] + bb["height"] <= 800, bb)
            st_bb = await page.locator('[data-testid="rehearsal-status"]').bounding_box()
            ctl_bb = await page.locator('[data-testid="rehearsal-controls"]').bounding_box()
            ok("status not hidden under controls", st_bb["y"] + st_bb["height"] <= ctl_bb["y"], (st_bb, ctl_bb["y"]))
            for t in ("done-speaking-btn", "rehearsal-script-panel"):
                if await page.locator(f'[data-testid="{t}"]').count():
                    bb = await page.locator(f'[data-testid="{t}"]').bounding_box()
                    print(t, bb, "bottom", bb["y"] + bb["height"], "controls top", ctl_bb["y"])
            scroll_y = await page.evaluate("window.scrollY")
            print("scrollY:", scroll_y)
            await asyncio.sleep(4)
            if await page.locator('[data-testid="live-transcript"]').count():
                lt = page.locator('[data-testid="live-transcript"]')
                h = (await lt.bounding_box())["height"]
                lh = await lt.evaluate("e => parseFloat(getComputedStyle(e).lineHeight)")
                ok("live transcript ≤2 lines", h <= lh * 2 + 2, f"h={h} lh={lh} text={await lt.inner_text()!r}")
            else:
                print("live-transcript not shown")
            # sentence-level advance info
            print("data-sentence:", await w.get_attribute("data-sentence"))
            await page.screenshot(path=f"{SS}/teleprompter.jpg", quality=40, type="jpeg")

            # ---- regressions ----
            await page.keyboard.press("?")
            await page.wait_for_timeout(500)
            ok("shortcuts overlay", await page.locator('[data-testid="shortcuts-overlay"]').count() > 0)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
            await page.click('[data-testid="skip-mode-toggle-btn"]')
            await page.wait_for_timeout(400)
            ok("skip badge on", await page.locator('[data-testid="skip-mode-badge"]').count() > 0)
            await page.click('[data-testid="skip-mode-toggle-btn"]')
            await page.wait_for_timeout(400)
            ok("skip badge off", await page.locator('[data-testid="skip-mode-badge"]').count() == 0)
            await page.click('[data-testid="current-line-edit-btn"]')
            await page.wait_for_selector('[data-testid="line-editor"]', timeout=5000)
            ok("line editor chars", await page.locator('[data-testid^="line-editor-character-"]').count() >= 2)
            await page.click('[data-testid="line-editor-cancel"]')
            await page.wait_for_timeout(500)
            panel = page.locator('[data-testid="rehearsal-script-panel"]')
            ln = panel.locator('[data-testid^="script-line-"]').filter(has_text="Talvez")
            await ln.first.click(force=True)
            await page.wait_for_timeout(400)
            jb = panel.locator('[data-testid^="jump-here-btn-"]')
            n = await jb.count()
            if n:
                last = jb.nth(n - 1)
                tid = await last.get_attribute("data-testid")
                print("btn visible:", await last.is_visible(), await last.bounding_box())
                await last.click()
                await page.wait_for_timeout(3000)
                await page.screenshot(path=f"{SS}/jump.jpg", quality=40, type="jpeg")
                print("toasts:", await page.locator("[data-sonner-toast]").all_text_contents())
                txt = await page.locator('[data-testid="current-line"]').inner_text()
                ok("jump-here works", "Talvez" in txt or "Fizeste" in txt or "Depois fui" in txt, f"{tid} -> {txt[:60]!r}")
                ok("short line full mode", await page.locator('[data-testid="current-line-window"]').get_attribute("data-mode") == "full")
            else:
                ok("jump-here btn present", False)
        except Exception as e:
            ok("exception", False, str(e)[:300])
            await page.screenshot(path=f"{SS}/reh_err.jpg", quality=40, type="jpeg")
        print("page errors:", errs)
        await b.close()
    c.delete(f"{API}/scripts/{sid}")
    print(f"{sum(x for _, x in R)}/{len(R)} passed")


asyncio.run(main())
