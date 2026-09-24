import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CategoryNode } from "@/lib/catalog";

// Задача 1: фото разделов на индексе каталога остаются полноцветными в обеих темах.
// Проверка по классам, потому что тёмная тема — это dark:-варианты Tailwind: любой
// opacity/filter/blend на картинке или её обёртке (в т. ч. dark:, group-hover:)
// приглушил бы фото. Затемнять можно только фон карточки.

const tree: CategoryNode[] = [
  "Электроинструмент",
  "Ручной инструмент",
  "Оснастка и расходники",
  "Измерительный инструмент",
  "Садовая техника",
  "Хозтовары",
].map((name, index) => ({
  id: index + 1,
  name,
  slug: `cat-${index + 1}`,
  sort_order: index,
  children: [],
}));

vi.mock("@/lib/catalog", () => ({
  getCategoryTreeOrNull: vi.fn(() => Promise.resolve(tree)),
}));
// Поиск и нижняя навигация к карточкам отношения не имеют (им нужен роутер).
vi.mock("@/components/layout/SearchBar", () => ({ SearchBar: () => null }));
vi.mock("@/components/layout/MobileBottomNav", () => ({ MobileBottomNav: () => null }));

import CatalogIndexPage from "./page";

const FORBIDDEN = [
  "opacity-",
  "grayscale",
  "brightness",
  "contrast",
  "saturate",
  "invert",
  "mix-blend",
  "filter",
];

function forbiddenClasses(element: Element): string[] {
  const tokens = (element.getAttribute("class") ?? "").split(/\s+/).filter(Boolean);
  return tokens.filter((token) => FORBIDDEN.some((bad) => token.includes(bad)));
}

function forbiddenStyles(element: Element): string[] {
  const style = (element as HTMLElement).style;
  return (["opacity", "filter", "mixBlendMode"] as const).filter((prop) => style[prop] !== "");
}

describe("Индекс каталога: фото разделов в тёмной теме (задача 1)", () => {
  it("у картинки карточки и её обёрток нет приглушающих классов и стилей", async () => {
    const { container } = render(await CatalogIndexPage());

    const images = [...container.querySelectorAll('img[src*="/catalog/categories/"]')];
    // Крупные (первый ряд) и обычные карточки — у обоих вариантов свои классы обёртки.
    expect(images.length).toBe(tree.length);

    for (const image of images) {
      const card = image.closest("a");
      expect(card).not.toBeNull();
      // Сама картинка, её обёртка и все предки до ссылки-карточки включительно.
      for (let node: Element | null = image; node; node = node.parentElement) {
        expect(forbiddenClasses(node), node.outerHTML.slice(0, 120)).toEqual([]);
        expect(forbiddenStyles(node), node.outerHTML.slice(0, 120)).toEqual([]);
        if (node === card) break;
      }
    }
  });

  // Плитки не должны сливаться с фоном в тёмной теме: плитка — bg-card (как
  // карточки товаров), страница в тёмной теме — общий фон сайта (canvas).
  it("плитка раздела отличается от фона страницы в тёмной теме", async () => {
    const { container } = render(await CatalogIndexPage());

    const main = container.querySelector("main")!;
    expect(main.className.split(/\s+/)).toContain("dark:bg-canvas");
    for (const image of container.querySelectorAll('img[src*="/catalog/categories/"]')) {
      const tile = image.closest("a")!;
      const tokens = tile.className.split(/\s+/);
      expect(tokens).toContain("bg-card");
      expect(tokens).not.toContain("bg-surface");
    }
  });

  it("проверка ловит приглушение с префиксами вариантов", () => {
    const probe = document.createElement("div");
    probe.className = "object-contain dark:opacity-80 group-hover:grayscale dark:mix-blend-multiply";
    expect(forbiddenClasses(probe)).toEqual([
      "dark:opacity-80",
      "group-hover:grayscale",
      "dark:mix-blend-multiply",
    ]);
  });
});
