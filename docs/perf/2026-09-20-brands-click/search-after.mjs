const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const list = await (await fetch(`http://127.0.0.1:9444/json/list`)).json();
const ws = new WebSocket(list.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (e) => (await send("Runtime.evaluate", { expression: e, returnByValue: true })).result?.result?.value;
await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
const out = [];
for (let run = 0; run < 5; run++) {
  await send("Page.navigate", { url: "http://127.0.0.1:3078/" });
  for (let i = 0; i < 80; i++) { if (await ev(`(()=>{const m=document.querySelector('main');return !!m&&Object.keys(m).some(k=>k.startsWith('__reactFiber'))})()`)) break; await sleep(250); }
  await sleep(800);
  const pos = await ev(`(()=>{const i=document.querySelector('header input[type="search"],header input');if(!i)return null;const r=i.getBoundingClientRect();return {x:r.left+20,y:r.top+r.height/2}})()`);
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: pos.x, y: pos.y, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: pos.x, y: pos.y, button: "left", clickCount: 1 });
  await send("Input.insertText", { text: "metabo" });
  const tc = Date.now();
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: "\r" });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
  let fb = null, done = null;
  for (let i = 0; i < 200; i++) {
    const s = await ev(`(()=>({href:location.href,busy:!!document.querySelector('main[aria-busy="true"]'),h1:(document.querySelector('h1')||{}).textContent||''}))()`);
    const dt = Date.now() - tc;
    if (fb == null && (s.busy || s.href.includes('/search'))) fb = dt;
    if (/Результаты/.test(s.h1)) { done = dt; break; }
    await sleep(50);
  }
  out.push({ run, feedbackMs: fb, contentMs: done }); console.error(JSON.stringify(out.at(-1)));
}
console.log(JSON.stringify(out)); ws.close();
