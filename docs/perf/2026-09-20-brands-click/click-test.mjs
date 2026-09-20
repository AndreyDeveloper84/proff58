// CDP: настоящие Input-события по плиткам «Популярные бренды». Только чтение.
const PORT = process.env.PORT || 9444;
const BASE = process.env.BASE || "https://proff58.ru";
const MOBILE = process.env.MOBILE === "1";
const THROTTLE = process.env.THROTTLE === "1";
const RUNS = Number(process.env.RUNS || 10);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const page = list.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const events = [];
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } else if (d.method) events.push(d); };
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result?.result?.value;

await send("Page.enable"); await send("Runtime.enable"); await send("Network.enable"); await send("Log.enable");
if (MOBILE) await send("Emulation.setDeviceMetricsOverride", { width: 375, height: 812, deviceScaleFactor: 2, mobile: true });
else await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
if (MOBILE) await send("Emulation.setTouchEmulationEnabled", { enabled: true });
if (THROTTLE) await send("Network.emulateNetworkConditions", { offline: false, latency: 300, downloadThroughput: 200 * 1024, uploadThroughput: 90 * 1024 });

const results = [];
for (let run = 0; run < RUNS; run++) {
  const cold = run % 2 === 0;
  if (cold) { await send("Network.clearBrowserCache"); await send("Network.clearBrowserCookies"); }
  events.length = 0;
  const t0 = Date.now();
  await send("Page.navigate", { url: BASE + "/" });
  // ждём гидратацию: ключ __reactFiber на main
  let hydrated = null;
  for (let i = 0; i < 120; i++) {
    const ok = await ev(`(()=>{const m=document.querySelector('main');return !!m&&Object.keys(m).some(k=>k.startsWith('__reactFiber'))})()`);
    if (ok) { hydrated = Date.now() - t0; break; }
    await sleep(250);
  }
  const info = await ev(`(()=>{const links=[...document.querySelectorAll('a[aria-label^="Товары бренда"]')];const a=links[${run} % Math.max(links.length,1)];if(!a)return null;a.scrollIntoView({block:'center'});const r=a.getBoundingClientRect();const x=r.left+r.width/2,y=r.top+r.height/2;const top=document.elementFromPoint(x,y);return {x,y,href:a.getAttribute('href'),label:a.getAttribute('aria-label'),covered:!(a===top||a.contains(top)),topTag:top&&top.tagName+'.'+(top.className||'').toString().slice(0,60)}})()`);
  if (!info) { results.push({ run, cold, error: "нет плиток брендов" }); continue; }
  await sleep(300);
  const before = await ev("location.href");
  const tc = Date.now();
  if (MOBILE) {
    await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: info.x, y: info.y }] });
    await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  } else {
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: info.x, y: info.y });
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: info.x, y: info.y, button: "left", clickCount: 1 });
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: info.x, y: info.y, button: "left", clickCount: 1 });
  }
  let urlChanged = null, content = null, feedback = null;
  for (let i = 0; i < 240; i++) {
    const s = await ev(`(()=>({href:location.href,h1:(document.querySelector('h1')||{}).textContent||'',busy:!!document.querySelector('[aria-busy="true"],.animate-pulse')}))()`);
    const dt = Date.now() - tc;
    if (feedback == null && (s.busy || s.href !== before)) feedback = dt;
    if (urlChanged == null && s.href !== before) urlChanged = dt;
    if (s.href !== before && /Результаты|Товары|Поиск/.test(s.h1)) { content = dt; break; }
    await sleep(100);
  }
  const errors = events.filter((e) => e.method === "Runtime.exceptionThrown" || (e.method === "Log.entryAdded" && e.params.entry.level === "error")).map((e) => (e.params.entry?.text || e.params.exceptionDetails?.text || "").slice(0, 160));
  results.push({ run, cold, brand: info.label, href: info.href, covered: info.covered, topTag: info.topTag, hydratedMs: hydrated, feedbackMs: feedback, urlChangedMs: urlChanged, contentMs: content, errors });
  console.error(JSON.stringify(results.at(-1)));
}
console.log(JSON.stringify({ base: BASE, mobile: MOBILE, throttle: THROTTLE, results }, null, 1));
ws.close();
