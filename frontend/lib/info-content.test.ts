import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { INFO_PAGES, INFO_PAGE_SLUGS } from "./info-content";

// Содержимое страниц лежит в коде, поэтому опечатка в пути к картинке или
// потерянная секция ловятся только здесь — админка и API их больше не проверяют.

describe("Страницы из кода", () => {
  it("все четыре на месте и открываются шапкой", () => {
    expect(INFO_PAGE_SLUGS).toEqual(["about", "delivery", "payment", "warranty"]);

    for (const slug of INFO_PAGE_SLUGS) {
      const page = INFO_PAGES[slug];
      expect(page.title, slug).toBeTruthy();
      expect(page.sections[0]?.layout, slug).toBe("hero");
    }
  });

  it("каждая картинка действительно лежит в public", () => {
    const paths: string[] = [];
    for (const page of Object.values(INFO_PAGES)) {
      for (const section of page.sections) {
        if (section.meta.image) paths.push(section.meta.image);
        paths.push(...(section.meta.images ?? []));
        for (const item of section.items) if (item.image) paths.push(item.image);
      }
    }

    expect(paths.length).toBeGreaterThan(0);
    for (const path of paths) {
      expect(existsSync(join(process.cwd(), "public", path)), path).toBe(true);
    }
  });

  it("у страниц заполнены заголовок и описание для поисковика", () => {
    for (const slug of INFO_PAGE_SLUGS) {
      expect(INFO_PAGES[slug].metaTitle, slug).toBeTruthy();
      expect(INFO_PAGES[slug].metaDescription, slug).toBeTruthy();
    }
  });
});
