import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
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

  // Ширина из заголовка webp: простой (VP8), без потерь (VP8L), расширенный (VP8X).
  function webpWidth(path: string): number {
    const buf = readFileSync(path);
    const chunk = buf.toString("ascii", 12, 16);
    if (chunk === "VP8 ") return buf.readUInt16LE(26) & 0x3fff;
    if (chunk === "VP8L") return (buf.readUInt32LE(21) & 0x3fff) + 1;
    if (chunk === "VP8X") return buf.readUIntLE(24, 3) + 1;
    throw new Error(`${path}: не webp (${chunk})`);
  }

  // DRF-2493: превью с увеличением при наведении рисуются из миниатюры. Исходник
  // 1254 px браузер ужимал в ~12 раз прямо во время анимации — фото шло зерном.
  it("у каждой статьи есть миниатюра обложки не шире 400 px", () => {
    for (const article of ARTICLES) {
      expect(article.thumb, article.slug).toMatch(/^\/[\w/-]+\.webp$/);
      expect(article.thumb, article.slug).not.toBe(article.image);
      const file = join(process.cwd(), "public", article.thumb!);
      expect(existsSync(file), article.slug).toBe(true);
      expect(webpWidth(file), article.slug).toBeLessThanOrEqual(400);
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
