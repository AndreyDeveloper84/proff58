import { afterEach, describe, expect, it, vi } from "vitest";
import { formatDateLabel } from "./articles-source";

describe("formatDateLabel", () => {
  it("переводит ISO-дату в человеческую", () => {
    expect(formatDateLabel("2026-07-20")).toBe("20 июля 2026");
  });

  it("убирает ведущий ноль у числа", () => {
    expect(formatDateLabel("2026-01-05")).toBe("5 января 2026");
  });

  it("пустая или кривая дата — пустая подпись, а не «Invalid Date»", () => {
    expect(formatDateLabel("")).toBe("");
    expect(formatDateLabel("вчера")).toBe("");
  });
});

describe("источник статей", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("без бэкенда показывает встроенные статьи, а не пустоту", async () => {
    vi.stubEnv("INTERNAL_API_BASE_URL", "");
    const { getArticleCards } = await import("./articles-source");

    const cards = await getArticleCards();

    expect(cards.length).toBeGreaterThan(0);
  });

  it("сбой API не роняет ленту — остаются встроенные", async () => {
    vi.stubEnv("INTERNAL_API_BASE_URL", "http://web:8000");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("нет сети"))),
    );
    const { getArticleCards } = await import("./articles-source");

    expect((await getArticleCards()).length).toBeGreaterThan(0);
  });

  it("статья из админки перекрывает одноимённую встроенную", async () => {
    vi.stubEnv("INTERNAL_API_BASE_URL", "http://web:8000");
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                slug: "sds-plus-ili-sds-max",
                title: "Версия из админки",
                excerpt: "",
                tag: "",
                figure: "",
                image: "",
                date: "2026-07-25",
                readingMinutes: 3,
              },
            ]),
        } as Response),
      ),
    );
    const { getArticleCards } = await import("./articles-source");

    const cards = await getArticleCards();
    const совпадения = cards.filter((c) => c.slug === "sds-plus-ili-sds-max");

    expect(совпадения).toHaveLength(1);
    expect(совпадения[0].title).toBe("Версия из админки");
  });

  it("лента отсортирована свежими вперёд", async () => {
    vi.stubEnv("INTERNAL_API_BASE_URL", "");
    const { getArticleCards } = await import("./articles-source");

    const dates = (await getArticleCards()).map((c) => c.date);

    expect([...dates].sort().reverse()).toEqual(dates);
  });

  it("неизвестный slug даёт null — страница отдаст 404", async () => {
    vi.stubEnv("INTERNAL_API_BASE_URL", "");
    const { getArticleBySlug } = await import("./articles-source");

    expect(await getArticleBySlug("нет-такой")).toBeNull();
  });
});
