// Прокси перед Django для имитации медленного/зависшего/ошибочного API.
// MODE=delay (DELAY_MS) | hang | error. Режим переключается на лету: GET /__mode?m=hang
import http from "node:http";
const TARGET = new URL(process.env.TARGET || "http://127.0.0.1:8077");
let mode = process.env.MODE || "delay";
let delay = Number(process.env.DELAY_MS || 2000);
http.createServer((req, res) => {
  if (req.url.startsWith("/__mode")) {
    const u = new URL(req.url, "http://x");
    mode = u.searchParams.get("m") || mode;
    delay = Number(u.searchParams.get("d") || delay);
    res.end(`${mode} ${delay}`);
    return;
  }
  // Медленным/сломанным делаем только каталог: тема и инфо-страницы layout'а не трогаем.
  const catalog = req.url.startsWith("/api/catalog/products") || req.url.startsWith("/api/catalog/brands") || req.url.startsWith("/api/catalog/search");
  const forward = () => {
    const p = http.request({ host: TARGET.hostname, port: TARGET.port, path: req.url, method: req.method, headers: { ...req.headers, host: TARGET.host } }, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
    p.on("error", () => { res.statusCode = 502; res.end(); });
    req.pipe(p);
  };
  if (!catalog) return forward();
  if (mode === "hang") return; // не отвечаем вовсе
  if (mode === "error") { res.statusCode = 500; res.end('{"detail":"boom"}'); return; }
  setTimeout(forward, delay);
}).listen(Number(process.env.PORT || 8078), "127.0.0.1", () => console.log("proxy up"));
