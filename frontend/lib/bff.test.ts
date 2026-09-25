import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

// INTERNAL_API_BASE_URL читается в bff.ts один раз на уровне модуля, поэтому
// env нужно выставить ДО импорта — используем resetModules + динамический import.
async function loadProxyToDjango() {
  vi.resetModules();
  const mod = await import("./bff");
  return mod.proxyToDjango;
}

// 204/205/304 — null-body-статусы: fetch Response запрещает тело (даже пустое)
// для них, поэтому proxyToDjango обязан отдавать null явно, а не читать
// upstream.arrayBuffer() вслепую (иначе new Response() бросает TypeError).
describe("proxyToDjango", () => {
  const originalFetch = global.fetch;
  const originalEnv = process.env.INTERNAL_API_BASE_URL;

  afterEach(() => {
    global.fetch = originalFetch;
    process.env.INTERNAL_API_BASE_URL = originalEnv;
  });

  it("проксирует 204 без тела, не бросая исключение", async () => {
    process.env.INTERNAL_API_BASE_URL = "http://web:8000";
    global.fetch = vi.fn().mockResolvedValue(
      new Response(null, { status: 204, headers: {} }),
    ) as unknown as typeof fetch;
    const proxyToDjango = await loadProxyToDjango();

    const request = new NextRequest("http://localhost:3000/api/whatever", {
      headers: { cookie: "sessionid=abc" },
    });

    const response = await proxyToDjango(request, "/api/whatever/", { method: "DELETE" });

    expect(response.status).toBe(204);
    expect((await response.arrayBuffer()).byteLength).toBe(0);
  });

  it("проксирует обычный JSON-ответ с телом как раньше", async () => {
    process.env.INTERNAL_API_BASE_URL = "http://web:8000";
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "active" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    ) as unknown as typeof fetch;
    const proxyToDjango = await loadProxyToDjango();

    const request = new NextRequest("http://localhost:3000/api/whatever", {
      headers: { cookie: "sessionid=abc" },
    });

    const response = await proxyToDjango(request, "/api/whatever/", { method: "POST", body: "{}" });

    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ status: "active" });
  });

  // PDF-счёт: без проброса Content-Disposition браузер открыл бы документ во вкладке,
  // а не сохранил файлом.
  it("пробрасывает Content-Disposition для файлов на скачивание", async () => {
    process.env.INTERNAL_API_BASE_URL = "http://web:8000";
    global.fetch = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
        status: 200,
        headers: {
          "content-type": "application/pdf",
          "content-disposition": 'attachment; filename="invoice-1.pdf"',
        },
      }),
    ) as unknown as typeof fetch;
    const proxyToDjango = await loadProxyToDjango();

    const request = new NextRequest("http://localhost:3000/api/orders/1/invoice");
    const response = await proxyToDjango(request, "/api/orders/1/invoice/", { method: "GET" });

    expect(response.headers.get("content-type")).toBe("application/pdf");
    expect(response.headers.get("content-disposition")).toContain("attachment");
    expect(new Uint8Array(await response.arrayBuffer())[0]).toBe(0x25);
  });
});
