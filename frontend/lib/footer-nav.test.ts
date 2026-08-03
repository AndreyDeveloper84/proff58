import { describe, expect, it } from "vitest";

import type { CategoryNode } from "./adapters";
import { FOOTER_CATEGORY_LIMIT, pickFooterCategories } from "./footer-nav";

function node(slug: string, name: string): CategoryNode {
  return { id: slug.length, name, slug, sort_order: 0, children: [] };
}

const TREE: CategoryNode[] = [
  node("avto", "Автоинструмент"),
  node("osnastka", "Оснастка и расходные материалы"),
  node("ruchnoy", "Ручной инструмент"),
  node("elektroinstrument", "Электроинструмент"),
  node("stroitelnyy", "Строительный и отделочный инструмент"),
  node("svarka", "Сварочное оборудование"),
];

describe("pickFooterCategories", () => {
  it("берёт приоритетные разделы в заданном порядке, а не первые из дерева", () => {
    expect(pickFooterCategories(TREE)).toEqual([
      { label: "Оснастка и расходные материалы", href: "/catalog/osnastka" },
      { label: "Ручной инструмент", href: "/catalog/ruchnoy" },
      { label: "Электроинструмент", href: "/catalog/elektroinstrument" },
      { label: "Строительный и отделочный инструмент", href: "/catalog/stroitelnyy" },
    ]);
  });

  it("подписи берёт из дерева — переименование в админке доходит до подвала", () => {
    const renamed = TREE.map((n) =>
      n.slug === "osnastka" ? node("osnastka", "Расходка") : n,
    );
    expect(pickFooterCategories(renamed)[0]).toEqual({
      label: "Расходка",
      href: "/catalog/osnastka",
    });
  });

  it("добирает другими корнями, если приоритетного раздела в дереве нет", () => {
    const partial = TREE.filter((n) => n.slug !== "ruchnoy" && n.slug !== "stroitelnyy");
    const picked = pickFooterCategories(partial);
    // Ссылок всё равно четыре, и все ведут в существующие разделы.
    expect(picked).toHaveLength(FOOTER_CATEGORY_LIMIT);
    for (const link of picked) {
      const slug = link.href.replace("/catalog/", "");
      expect(partial.some((n) => n.slug === slug)).toBe(true);
    }
  });

  it("не дублирует раздел, попавший и в приоритет, и в добор", () => {
    const picked = pickFooterCategories(TREE);
    expect(new Set(picked.map((l) => l.href)).size).toBe(picked.length);
  });

  it("дерево недоступно или пустое → пусто (в подвале останется «Все категории»)", () => {
    expect(pickFooterCategories(null)).toEqual([]);
    expect(pickFooterCategories([])).toEqual([]);
  });
});
