import { describe, expect, it } from "vitest";

import { ARTICLES, articleSlugs, getArticle } from "./articles";

describe("статьи каталога", () => {
  it("slug уникальны — иначе две статьи делят один адрес", () => {
    const slugs = articleSlugs();
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it("каждая статья заполнена: лид, «коротко», секции с блоками", () => {
    for (const article of ARTICLES) {
      expect(article.title.length, article.slug).toBeGreaterThan(10);
      expect(article.excerpt.length, article.slug).toBeGreaterThan(30);
      expect(article.summary.length, article.slug).toBeGreaterThanOrEqual(3);
      expect(article.sections.length, article.slug).toBeGreaterThan(0);
      for (const section of article.sections) {
        expect(section.blocks.length, `${article.slug} / ${section.heading}`).toBeGreaterThan(0);
      }
    }
  });

  // Обложки берём из ассетов категорий каталога — путь должен быть локальным,
  // иначе картинка не пройдёт через images.unoptimized и CSP.
  it("обложки ссылаются на локальные ассеты", () => {
    for (const article of ARTICLES) {
      expect(article.image, article.slug).toMatch(/^\/[\w/-]+\.(webp|png|jpg)$/);
    }
  });

  it("таблицы согласованы: в каждой строке столько же ячеек, сколько в шапке", () => {
    for (const article of ARTICLES) {
      for (const section of article.sections) {
        for (const block of section.blocks) {
          if (block.kind !== "table") continue;
          for (const row of block.rows) {
            expect(row.length, `${article.slug} / ${section.heading}`).toBe(block.head.length);
          }
        }
      }
    }
  });

  it("getArticle находит статью по slug и возвращает null для чужого", () => {
    expect(getArticle(ARTICLES[0].slug)?.title).toBe(ARTICLES[0].title);
    expect(getArticle("net-takoy-stati")).toBeNull();
  });
});
