import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getLoginOAuthProviders } from "./oauth-providers";

// SSR-загрузчик провайдеров страницы входа: любая беда — пустой список.
describe("getLoginOAuthProviders", () => {
  const originalFetch = global.fetch;
  const originalEnv = process.env.INTERNAL_API_BASE_URL;
  const fetchMock = vi.fn();

  beforeEach(() => {
    process.env.INTERNAL_API_BASE_URL = "http://web:8000/";
    fetchMock.mockClear();
    global.fetch = fetchMock as unknown as typeof fetch;
  });
  afterEach(() => {
    global.fetch = originalFetch;
    process.env.INTERNAL_API_BASE_URL = originalEnv;
  });

  it("берёт включённых провайдеров из Django, с таймаутом", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(Response.json({ providers: [{ id: "vkid" }, { id: "yandex" }] })),
    );

    await expect(getLoginOAuthProviders()).resolves.toEqual(["vkid", "yandex"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://web:8000/api/oauth/providers/");
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.headers["X-Forwarded-Proto"]).toBe("https");
  });

  it("неизвестные провайдеры и дубли отбрасывает, порядок — vkid, yandex", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        Response.json({ providers: [{ id: "yandex" }, { id: "google" }, { id: "vkid" }, { id: "yandex" }] }),
      ),
    );

    await expect(getLoginOAuthProviders()).resolves.toEqual(["vkid", "yandex"]);
  });

  it("без INTERNAL_API_BASE_URL — [] и без запроса", async () => {
    delete process.env.INTERNAL_API_BASE_URL;

    await expect(getLoginOAuthProviders()).resolves.toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("таймаут (AbortSignal) — []", async () => {
    fetchMock.mockImplementation(() =>
      Promise.reject(new DOMException("The operation was aborted due to timeout", "TimeoutError")),
    );

    await expect(getLoginOAuthProviders()).resolves.toEqual([]);
  });

  it("5xx — []", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("oops", { status: 502 })));

    await expect(getLoginOAuthProviders()).resolves.toEqual([]);
  });

  it("не JSON / не тот формат — []", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("<html>", { status: 200 })));
    await expect(getLoginOAuthProviders()).resolves.toEqual([]);

    fetchMock.mockImplementation(() => Promise.resolve(Response.json({ providers: "vkid" })));
    await expect(getLoginOAuthProviders()).resolves.toEqual([]);
  });
});
