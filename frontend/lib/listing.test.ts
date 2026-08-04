import { describe, expect, it } from "vitest";

import { categoryNav, normalizeRangeFilters } from "./listing";
import type { Facet, Listing } from "./types";

function navFacet(options: { value: string; label: string; count: number }[]): Facet {
  return {
    code: "tool_type",
    label: "Тип инструмента",
    type: "checkbox",
    isNav: true,
    kind: "nav",
    options: options.map((o) => ({ ...o, selected: false })),
  };
}

function listing(patch: Partial<Listing> = {}): Listing {
  return {
    category: { title: "Раздел", intro: "", breadcrumb: [] },
    subcategories: [],
    facets: [],
    sort: [],
    total: 0,
    page: 1,
    perPage: 24,
    products: [],
    ...patch,
  };
}

describe("categoryNav", () => {
  it("отдаёт подкатегории ссылками и не дублирует их типами", () => {
    const nav = categoryNav(
      listing({
        subcategories: [
          { label: "Отвёртки", href: "/catalog/ruchnoy-otvertki" },
          { label: "Ключи", href: "/catalog/ruchnoy-klyuchi" },
        ],
        facets: [navFacet([{ value: "drel", label: "Дрели", count: 5 }])],
      }),
      "ruchnoy",
    );

    expect(nav).toEqual({
      title: "Разделы",
      isNavigation: true,
      items: [
        { key: "/catalog/ruchnoy-otvertki", label: "Отвёртки", href: "/catalog/ruchnoy-otvertki", active: false },
        { key: "/catalog/ruchnoy-klyuchi", label: "Ключи", href: "/catalog/ruchnoy-klyuchi", active: false },
      ],
    });
  });

  it("на «Электроинструменте» навигация идёт типами, а не деревом", () => {
    const nav = categoryNav(
      listing({
        subcategories: [{ label: "Дрели", href: "/catalog/dreli" }],
        facets: [navFacet([{ value: "perforatory", label: "Перфораторы", count: 140 }])],
      }),
      "elektroinstrument",
      "perforatory",
    );

    expect(nav?.isNavigation).toBe(false);
    expect(nav?.title).toBe("Тип инструмента");
    expect(nav?.items).toEqual([
      { key: "perforatory", label: "Перфораторы", count: 140, active: true },
    ]);
  });

  it("возвращает активный тип синтетическим пунктом, если он вымылся фильтрами", () => {
    const nav = categoryNav(
      listing({ facets: [navFacet([{ value: "dreli", label: "Дрели", count: 3 }])] }),
      "elektroinstrument",
      "shtroborezy",
    );

    // Подпись — humanizeToken(slug): своего label у «вымытого» типа в выдаче уже нет.
    expect(nav?.items.at(-1)).toEqual({
      key: "shtroborezy",
      label: "Shtroborezy",
      count: 0,
      active: true,
    });
  });

  it("без подкатегорий и без nav-фасета блока нет", () => {
    expect(categoryNav(listing(), "ruchnoy-otvertki")).toBeNull();
  });
});

describe("normalizeRangeFilters", () => {
  const priceFacet = (min: number, max: number): Facet => ({
    code: "price",
    label: "Цена",
    type: "range",
    unit: "₽",
    kind: "base",
    min,
    max,
  });

  // Тот самый баг: цена выставлена на прошлом типе (до 15 595 ₽), после
  // переключения на «Аппараты сварки пластиковых труб» шкала — 980…3 850.
  it("снимает верхнюю границу, которая выше всей выдачи", () => {
    expect(normalizeRangeFilters({ price: { max: 15595 } }, [priceFacet(980, 3850)])).toEqual({});
  });

  it("снимает нижнюю границу, которая ниже всей выдачи", () => {
    expect(normalizeRangeFilters({ price: { min: 500 } }, [priceFacet(980, 3850)])).toEqual({});
  });

  it("оставляет границу, которая реально сужает выдачу", () => {
    expect(normalizeRangeFilters({ price: { min: 500, max: 2000 } }, [priceFacet(980, 3850)])).toEqual(
      { price: { min: undefined, max: 2000 } },
    );
  });

  // Пустой результат — честное состояние с точечным сбросом, а не повод молча
  // переписать выбор человека.
  it("не трогает границу, которая обнуляет выдачу", () => {
    expect(normalizeRangeFilters({ price: { min: 9000 } }, [priceFacet(980, 3850)])).toBeNull();
  });

  it("ничего не меняет, когда границы в шкале — второй проход холостой", () => {
    expect(normalizeRangeFilters({ price: { max: 2000 } }, [priceFacet(980, 3850)])).toBeNull();
  });

  it("не судит о фасете, которого нет в выдаче или он без шкалы", () => {
    expect(normalizeRangeFilters({ price: { max: 15595 } }, [])).toBeNull();
    expect(
      normalizeRangeFilters({ attr_weight: { max: 10 } }, [
        { code: "attr_weight", label: "Вес", type: "range" },
      ]),
    ).toBeNull();
  });

  it("чекбоксы переносит как есть", () => {
    expect(
      normalizeRangeFilters({ brand: ["bosch"], price: { max: 15595 } }, [priceFacet(980, 3850)]),
    ).toEqual({ brand: ["bosch"] });
  });
});
