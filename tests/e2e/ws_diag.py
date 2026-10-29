import asyncio
import sys
from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://4a235a53-6d3b-4819-b215-3bfb5f6424cc.preview.emergentagent.com"
JS = """async (api) => {
  const cfg = await (await fetch(api + '/api/stt/deepgram-token', {method: 'POST'})).json();
  const q = new URLSearchParams(cfg.params);
  const out = [];
  const run = (label, url, protos) => new Promise((res) => {
    const t0 = performance.now();
    let ws;
    try { ws = new WebSocket(url, protos); } catch (e) { out.push(label + ' throw ' + e); return res(); }
    ws.onopen = () => { out.push(label + ' OPEN in ' + Math.round(performance.now() - t0) + 'ms proto=' + ws.protocol); ws.close(); res(); };
    ws.onerror = () => out.push(label + ' error');
    ws.onclose = (e) => { out.push(label + ' close ' + e.code + ' ' + e.reason); res(); };
    setTimeout(res, 8000);
  });
  await run('direct-bearer', cfg.url + '?' + q, ['bearer', cfg.token]);
  const q2 = new URLSearchParams(q); ['malandreco', 'arrota', 'Jean Genet'].forEach((k) => q2.append('keyterm', k));
  await run('direct-bearer-keyterms', cfg.url + '?' + q2, ['bearer', cfg.token]);
  const text = 'Porque não sabia se queria mesmo ir. Há dias em que partir parece a coisa mais fácil do mundo, e há outros em que pesa como uma pedra. Vou. Mas só se me prometeres que não ficas aqui sozinho à espera.';
  const words = text.toLowerCase().replace(/[^\\p{L}\\p{N}\\s-]/gu, ' ').split(/\\s+/).filter((w) => w.length >= 3);
  const phrases = text.split(/[.!?;]+/).map((p) => p.trim()).filter((p) => p.split(' ').length > 1);
  const q3 = new URLSearchParams(q); [...new Set(words), ...phrases].slice(0, 40).forEach((k) => q3.append('keyterm', k));
  await run('direct-app-hints(' + [...new Set(words), ...phrases].slice(0,40).length + ')', cfg.url + '?' + q3, ['bearer', cfg.token]);
  await run('proxy', api.replace('https', 'wss') + '/api/stt/deepgram?' + q2, undefined);
  return out;
}"""


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/root/bin/chromium", args=["--no-sandbox"])
        page = await b.new_page()
        page.on("console", lambda m: print("console:", m.text))
        await page.goto(URL)
        print("\n".join(await page.evaluate(JS, URL)))
        await b.close()

asyncio.run(main())
