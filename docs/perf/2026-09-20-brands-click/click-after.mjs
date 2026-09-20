// «После»: клик по плитке бренда на локальной production-сборке. Меряем время до
// ПЕРВОГО видимого отклика (полоса на плитке / скелетон / смена URL) и до контента.
const PORT = process.env.PORT || 9444;
const BASE = process.env.BASE || "http://127.0.0.1:3078";
const MOBILE = process.env.MOBILE === "1";
const RUNS = Number(process.env.RUNS || 10);
const EXPECT = process.env.EXPECT || "content"; // content | error
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const ws = new WebSocket(list.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const events = [];
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } else if (d.method) events.push(d); };
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true })).result?.result?.value;
await send("Page.enable"); await send("Runtime.enable"); await send("Network.enable"); await send("Log.enable");
await send("Emulation.setDeviceMetricsOverride", MOBILE ? { width: 375, height: 812, deviceScaleFactor: 2, mobile: true } : { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
if (MOBILE) await send("Emulation.setTouchEmulationEnabled", { enabled: true });
const results = [];
for (let run = 0; run < RUNS; run++) {
  const cold = run % 2 === 0;
  if (cold) { await send("Network.clearBrowserCache"); }
  events.length = 0;
  await send("Page.navigate", { url: BASE + "/" });
  for (let i = 0; i < 120; i++) { if (await ev(`(()=>{const m=document.querySelector('main');return !!m&&Object.keys(m).some(k=>k.startsWith('__reactFiber'))})()`)) break; await sleep(250); }
  await sleep(cold ? 300 : 1500); // тёплый прогон даёт префетчу отработать
  const info = await ev(`(()=>{const links=[...document.querySelectorAll('a[aria-label^="Товары бренда"]')];const a=links[${run} % Math.max(links.length,1)];if(!a)return null;a.scrollIntoView({block:'center'});const r=a.getBoundingClientRect();window.__a=a;return {x:r.left+r.width/2,y:r.top+r.height/2,href:a.getAttribute('href'),label:a.getAttribute('aria-label')}})()`);
  if (!info) { results.push({ run, error: "нет плиток" }); continue; }
  await sleep(200);
  const before = await ev("location.href");
  const tc = Date.now();
  if (MOBILE) { await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: info.x, y: info.y }] }); await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] }); }
  else { await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: info.x, y: info.y }); await send("Input.dispatchMouseEvent", { type: "mousePressed", x: info.x, y: info.y, button: "left", clickCount: 1 }); await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: info.x, y: info.y, button: "left", clickCount: 1 }); }
  let feedback = null, done = null, what = null;
  for (let i = 0; i < 400; i++) {
    const s = await ev(`(()=>{const a=window.__a;const bar=a&&a.isConnected?a.querySelector('span[aria-hidden]'):null;return {href:location.href,h1:(document.querySelector('h1')||{}).textContent||'',bar:!!bar&&getComputedStyle(bar).opacity!=='0',busy:!!document.querySelector('main [aria-busy="true"], main .animate-pulse'),alert:(document.querySelector('[role="alert"]')||{}).textContent||''}})()`);
    const dt = Date.now() - tc;
    if (feedback == null && (s.bar || s.busy || s.href !== before)) { feedback = dt; what = s.bar ? "полоса на плитке" : s.busy ? "скелетон" : "смена URL"; }
    if (EXPECT === "error" ? /Повторить|Не удалось/.test(s.alert) : (s.href !== before && /Товары/.test(s.h1))) { done = dt; break; }
    await sleep(50);
  }
  const errors = events.filter((e) => e.method === "Runtime.exceptionThrown").length;
  results.push({ run, cold, brand: info.label, href: info.href, feedbackMs: feedback, feedbackBy: what, doneMs: done, jsErrors: errors });
  console.error(JSON.stringify(results.at(-1)));
}
console.log(JSON.stringify({ base: BASE, mobile: MOBILE, expect: EXPECT, results }, null, 1));
ws.close();
