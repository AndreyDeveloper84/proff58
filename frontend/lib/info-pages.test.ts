import { afterEach, describe, expect, it, vi } from "vitest";
import { toParagraphs } from "./info-pages";

describe("toParagraphs", () => {
  it("делит текст на абзацы по пустой строке", () => {
    expect(toParagraphs("Первый\n\nВторой")).toEqual(["Первый", "Второй"]);
  });

  it("одиночные переводы строки оставляет внутри абзаца", () => {
    // Внутри абзаца перенос сохраняется вёрсткой (whitespace-pre-line).
    expect(toParagraphs("Строка\nещё строка")).toEqual(["Строка\nещё строка"]);
  });

  it("выкидывает пустые куски и пробелы", () => {
    expect(toParagraphs("Текст\n\n   \n\nЕщё")).toEqual(["Текст", "Ещё"]);
  });

  it("пустое тело даёт пустой список", () => {
    expect(toParagraphs("")).toEqual([]);
  });
});

describe("getInfoPageLinks", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("без базового URL возвращает пустой список, а не падает", async () => {
    vi.stubEnv("INTERNAL_API_BASE_URL", "");
    const { getInfoPageLinks } = await import("./info-pages");

    expect(await getInfoPageLinks()).toEqual([]);
  });

  it("сбой сети не роняет подвал", async () => {
    vi.stubEnv("INTERNAL_API_BASE_URL", "http://web:8000");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("сеть недоступна"))),
    );
    const { getInfoPageLinks } = await import("./info-pages");

    expect(await getInfoPageLinks()).toEqual([]);
  });

  it("несёт X-Forwarded-Proto — иначе Django редиректит серверный запрос", async () => {
    vi.stubEnv("INTERNAL_API_BASE_URL", "http://web:8000");
    const fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { getInfoPageLinks } = await import("./info-pages");

    await getInfoPageLinks();

    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      cache: "no-store",
      headers: { "X-Forwarded-Proto": "https" },
    });
  });
});
