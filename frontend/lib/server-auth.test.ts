import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// INTERNAL_API_BASE_URL читается на уровне модуля, поэтому модуль импортируется
// динамически после подмены env (тот же приём, что в lib/bff.test.ts).
async function load() {
  return (await import("./server-auth")).checkServerAuth;
}

describe("checkServerAuth", () => {
  const originalEnv = process.env.INTERNAL_API_BASE_URL;

  beforeEach(() => {
    vi.resetModules();
    process.env.INTERNAL_API_BASE_URL = "http://web:8000";
  });

  afterEach(() => {
    process.env.INTERNAL_API_BASE_URL = originalEnv;
    vi.unstubAllGlobals();
  });

  it("200 от Django — пускаем", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 200 })));
    const checkServerAuth = await load();

    await expect(checkServerAuth("sessionid=abc")).resolves.toBe("authenticated");
  });

  it("401/403 — гость", async () => {
    for (const status of [401, 403]) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status })));
      vi.resetModules();
      const checkServerAuth = await load();

      await expect(checkServerAuth("sessionid=abc")).resolves.toBe("anonymous");
    }
  });

  it("без cookie в Django не ходит — вошедших без них не бывает", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const checkServerAuth = await load();

    await expect(checkServerAuth("")).resolves.toBe("anonymous");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("500 — это не «вы не вошли»", async () => {
    // Иначе человека с живой сессией выбрасывало бы на форму входа за чужую ошибку.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    const checkServerAuth = await load();

    await expect(checkServerAuth("sessionid=abc")).resolves.toBe("unavailable");
  });

  it("обрыв связи — тоже не «вы не вошли»", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));
    const checkServerAuth = await load();

    await expect(checkServerAuth("sessionid=abc")).resolves.toBe("unavailable");
  });

  it("без настроенного адреса Django молча внутрь не пускаем и не выгоняем", async () => {
    delete process.env.INTERNAL_API_BASE_URL;
    vi.resetModules();
    const checkServerAuth = await load();

    await expect(checkServerAuth("sessionid=abc")).resolves.toBe("unavailable");
  });

  it("шлёт cookie и не кеширует ответ", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const checkServerAuth = await load();

    await checkServerAuth("sessionid=abc; csrftoken=xyz");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://web:8000/api/account/me/");
    expect(init.headers.cookie).toBe("sessionid=abc; csrftoken=xyz");
    expect(init.cache).toBe("no-store");
  });
});
