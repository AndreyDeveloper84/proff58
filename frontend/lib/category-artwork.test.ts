import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { toolTypeArtwork } from "./category-artwork";

// Карта картинок — обычный объект, поэтому опечатка в slug или потерянный файл
// выявляются только здесь: на витрине это тихо превратится в плитку без картинки.

describe("Картинки типов инструмента (DRF-996)", () => {
  const WITH_ARTWORK = [
    "dreli-shurupoverty",
    "shlifmashiny",
    "pily",
    "perforatory",
    "bolgarki-ushm",
    "gaikoverty",
    "lobziki",
    "feny",
    "gravery",
  ];

  it("для каждого типа из карты файл лежит в public", () => {
    for (const slug of WITH_ARTWORK) {
      const path = toolTypeArtwork(slug);
      expect(path, slug).toBe(`/catalog/tool-types/${slug}.webp`);
      expect(existsSync(join(process.cwd(), "public", path!)), slug).toBe(true);
    }
  });

  it("тип без картинки не выдумывает путь", () => {
    // Плитка таких типов рендерится текстом — это рабочее состояние, а не ошибка.
    expect(toolTypeArtwork("shtoborezy")).toBeNull();
    expect(toolTypeArtwork("pylesosy")).toBeNull();
    expect(toolTypeArtwork("выдуманный-тип")).toBeNull();
  });
});
