import { afterEach, describe, expect, it, vi } from "vitest";

import {
  productSeoMetadata,
  robotsPolicy,
  siteOrigin,
  sitemapApiBase,
  sitemapEntries,
} from "./seo";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("robotsPolicy", () => {
  it("по умолчанию (переменная не задана) закрывает всё", () => {
    expect(robotsPolicy({ indexing: undefined, host: "proff58.ru", origin: "https://proff58.ru" })).toEqual({
      rules: { userAgent: "*", disallow: "/" },
    });
  });

  it("неизвестное значение среды закрывает всё", () => {
    expect(robotsPolicy({ indexing: "staging", host: "proff58.ru", origin: "https://proff58.ru" })).toEqual({
      rules: { userAgent: "*", disallow: "/" },
    });
  });

  it("production на каноническом хосте открывает сайт и отдаёт sitemap", () => {
    expect(robotsPolicy({ indexing: "production", host: "proff58.ru", origin: "https://proff58.ru" })).toEqual({
      rules: { userAgent: "*", allow: "/", disallow: ["/api/", "/*?"] },
      sitemap: "https://proff58.ru/sitemap.xml",
    });
  });

  it("production, но чужой хост (dev., IP, localhost) — закрыто", () => {
    for (const host of ["dev.proff58.ru", "127.0.0.1:8082", "localhost:3000", null]) {
      expect(robotsPolicy({ indexing: "production", host, origin: "https://proff58.ru" })).toEqual({
        rules: { userAgent: "*", disallow: "/" },
      });
    }
  });
});

describe("siteOrigin", () => {
  it("берёт SITE_URL рантайма без хвостового слэша", () => {
    vi.stubEnv("SITE_URL", "https://proff58.ru/");
    expect(siteOrigin()).toBe("https://proff58.ru");
  });

  it("без SITE_URL — канонический домен", () => {
    vi.stubEnv("SITE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "");
    expect(siteOrigin()).toBe("https://proff58.ru");
  });
});

describe("productSeoMetadata", () => {
  it("title без суффикса (его дописывает шаблон layout), canonical по slug", () => {
    const md = productSeoMetadata({ name: "Перфоратор ЗУБР ЗП-2470", slug: "0110000197", seoIndexable: true });
    expect(md.title).toBe("Перфоратор ЗУБР ЗП-2470");
    expect(md.alternates).toEqual({ canonical: "/product/0110000197" });
    expect(md.robots).toEqual({ index: true, follow: true });
  });

  it("товар вне allowlist — noindex, но ссылки обходятся", () => {
    const md = productSeoMetadata({ name: "X", slug: "x", seoIndexable: false });
    expect(md.robots).toEqual({ index: false, follow: true });
  });
});

describe("sitemapEntries", () => {
  it("абсолютные канонические URL карточек с датой изменения", () => {
    expect(
      sitemapEntries([{ slug: "a", updated_at: "2026-09-20T10:00:00Z" }], "https://proff58.ru"),
    ).toEqual([{ url: "https://proff58.ru/product/a", lastModified: new Date("2026-09-20T10:00:00Z") }]);
  });

  it("slug экранируется", () => {
    expect(sitemapEntries([{ slug: "a b", updated_at: "2026-09-20T10:00:00Z" }], "https://proff58.ru")[0].url).toBe(
      "https://proff58.ru/product/a%20b",
    );
  });

  it("битая или пустая дата не роняет sitemap — запись остаётся без lastModified", () => {
    expect(
      sitemapEntries(
        [
          { slug: "a", updated_at: "не дата" },
          { slug: "b", updated_at: null },
          { slug: "c", updated_at: "" },
        ],
        "https://proff58.ru",
      ),
    ).toEqual([
      { url: "https://proff58.ru/product/a" },
      { url: "https://proff58.ru/product/b" },
      { url: "https://proff58.ru/product/c" },
    ]);
  });
});

describe("sitemapApiBase", () => {
  it("адрес API без хвостового слэша", () => {
    expect(sitemapApiBase({ INTERNAL_API_BASE_URL: "http://web:8000/" })).toBe("http://web:8000");
  });

  it("без адреса вне production — пустой sitemap (сборка, локалка)", () => {
    expect(sitemapApiBase({})).toBeNull();
    expect(sitemapApiBase({ SEO_INDEXING: "off" })).toBeNull();
  });

  // Пустой sitemap с кодом 200 краулер читает как «товаров больше нет».
  it("без адреса в production — ошибка, а не пустой список", () => {
    expect(() => sitemapApiBase({ SEO_INDEXING: "production" })).toThrow(/INTERNAL_API_BASE_URL/);
  });
});
