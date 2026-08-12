import { describe, expect, it } from "vitest";

import {
  categoryNav,
  filtersAfterToolTypeChange,
  normalizeRangeFilters,
  pricePresets,
  sidebarFacets,
  typeNavPanel,
} from "./listing";
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

describe("filtersAfterToolTypeChange", () => {
  // Жалоба «зашёл в раздел — цена сломана»: цена от прежнего типа приезжала
  // в новую выдачу, вешала чип и резала список.
  it("сбрасывает цену и характеристики", () => {
    expect(
      filtersAfterToolTypeChange({
        price: { max: 15595 },
        attr_disc_diameter: ["125"],
      }),
    ).toEqual({});
  });

  it("сохраняет бренд и наличие — они не про тип инструмента", () => {
    expect(
      filtersAfterToolTypeChange({
        brand: ["bosch"],
        stock: ["in_stock"],
        price: { min: 1000, max: 8000 },
      }),
    ).toEqual({ brand: ["bosch"], stock: ["in_stock"] });
  });

  it("на пустом наборе ничего не выдумывает", () => {
    expect(filtersAfterToolTypeChange({})).toEqual({});
  });
});

describe("typeNavPanel", () => {
  // Числа — срез стенда dev.proff58.ru от 09.08.2026 (DRF-991 §3).
  function typeNav(options: { value: string; label: string; count: number }[], toolType?: string) {
    return categoryNav(listing({ facets: [navFacet(options)] }), "kategoriya", toolType);
  }
  const panel = (options: { value: string; label: string; count: number }[], toolType?: string) =>
    typeNavPanel(typeNav(options, toolType), toolType);

  it("моно-тип панель не показывает: выбирать не из чего", () => {
    expect(panel([{ value: "domkraty", label: "Домкраты", count: 84 }])).toBeNull();
  });

  it("доминирующий тип панель не показывает — «Метчики» 99,6 %", () => {
    expect(
      panel([
        { value: "metchiki-plashki", label: "Метчики и плашки", count: 247 },
        { value: "prochaya-osnastka", label: "Прочая оснастка", count: 1 },
      ]),
    ).toBeNull();
  });

  // 97 % — ближайший к порогу реальный случай, на нём проверяем, что граница не «плывёт».
  it("«Отвёртки» 97 % — панели нет", () => {
    expect(
      panel([
        { value: "otvertki", label: "Отвёртки", count: 261 },
        { value: "molotki", label: "Молотки", count: 4 },
        { value: "nabory", label: "Наборы", count: 3 },
        { value: "prochee", label: "Прочее", count: 1 },
      ]),
    ).toBeNull();
  });

  it("«Электроинструмент» панель оставляет: 24,6 % у крупнейшего типа", () => {
    const result = panel([
      { value: "dreli", label: "Дрели и шуруповёрты", count: 337 },
      { value: "shlifmashiny", label: "Шлифовальные машины", count: 247 },
      { value: "pily", label: "Пилы", count: 150 },
      { value: "perforatory", label: "Перфораторы", count: 125 },
    ]);

    expect(result).not.toBeNull();
    expect(result?.items.map((i) => i.label)).toEqual([
      "Дрели и шуруповёрты",
      "Шлифовальные машины",
      "Пилы",
      "Перфораторы",
    ]);
  });

  // Бэк отдаёт порядок манифеста таксономии — при обрезке до 12 плиток самый
  // товарный тип уезжал под кнопку «Ещё».
  it("сортирует по количеству, а не по порядку от API", () => {
    const result = panel([
      { value: "gravery", label: "Граверы", count: 12 },
      { value: "dreli", label: "Дрели", count: 337 },
      { value: "pily", label: "Пилы", count: 150 },
    ]);

    expect(result?.items.map((i) => i.count)).toEqual([337, 150, 12]);
  });

  it("при равном количестве — по алфавиту", () => {
    const result = panel([
      { value: "pily", label: "Пилы", count: 40 },
      { value: "bolgarki", label: "Болгарки", count: 40 },
      { value: "dreli", label: "Дрели", count: 20 },
    ]);

    expect(result?.items.map((i) => i.label)).toEqual(["Болгарки", "Пилы", "Дрели"]);
  });

  // «Секаторы 1» и «Мотоблоки 1» в электроинструменте — след раскладки данных,
  // а не выбор для покупателя. Товары остаются в выдаче, скрыт только пункт.
  it("редкие типы (count < 3) в панель не попадают", () => {
    const result = panel([
      { value: "dreli", label: "Дрели", count: 337 },
      { value: "pily", label: "Пилы", count: 150 },
      { value: "sekatory", label: "Секаторы и сучкорезы", count: 1 },
      { value: "motobloki", label: "Мотоблоки и культиваторы", count: 1 },
      { value: "payalniki", label: "Паяльники", count: 2 },
    ]);

    expect(result?.items.map((i) => i.label)).toEqual(["Дрели", "Пилы"]);
  });

  // Доля считается до отсечения хвоста — иначе «79 + 1» стало бы моно-типом,
  // и один результат получался бы по двум разным причинам.
  it("хвост учитывается в доле, но не показывается", () => {
    expect(
      panel([
        { value: "domkraty", label: "Домкраты", count: 79 },
        { value: "vorotki", label: "Воротки", count: 1 },
      ]),
    ).toBeNull();
  });

  // Доля топа 71 % — правило C пропускает, но после порога остаётся одна плитка.
  it("после отсечения хвоста одна плитка — панели нет", () => {
    expect(
      panel([
        { value: "osnovnoy", label: "Основной", count: 10 },
        { value: "redkiy-a", label: "Редкий А", count: 2 },
        { value: "redkiy-b", label: "Редкий Б", count: 2 },
      ]),
    ).toBeNull();
  });

  it("выбранный тип убирает панель целиком (возврат даёт Блок 3)", () => {
    expect(
      panel(
        [
          { value: "dreli", label: "Дрели", count: 337 },
          { value: "pily", label: "Пилы", count: 150 },
        ],
        "dreli",
      ),
    ).toBeNull();
  });

  it("подкатегории проходят насквозь: приоритет дерева правила не трогают", () => {
    const nav = categoryNav(
      listing({
        subcategories: [{ label: "Отвёртки", href: "/catalog/otvertki" }],
        facets: [],
      }),
      "ruchnoy",
    );

    expect(typeNavPanel(nav)).toBe(nav);
  });

  it("нет навигации — нет и панели", () => {
    expect(typeNavPanel(null)).toBeNull();
  });
});

describe("pricePresets", () => {
  it("на широкой шкале доступны все четыре", () => {
    expect(pricePresets(70, 92000).map((p) => p.label)).toEqual([
      "до 3 000",
      "3 000 – 7 000",
      "7 000 – 15 000",
      "от 15 000",
    ]);
  });

  // «от 15 000» на выдаче, где всё дешевле 12 000, — кнопка, дающая ноль товаров.
  it("не предлагает диапазоны за пределами шкалы", () => {
    expect(pricePresets(500, 12000).map((p) => p.label)).toEqual([
      "до 3 000",
      "3 000 – 7 000",
      "7 000 – 15 000",
    ]);
  });

  // Пресет, который не отсекает ничего, normalizeRangeFilters всё равно сбросит —
  // нажатие выглядело бы как «ничего не произошло».
  it("не предлагает диапазон, который ничего не сужает", () => {
    expect(pricePresets(4000, 6000).map((p) => p.label)).toEqual([]);
  });

  it("шкалы нет — пресетов нет", () => {
    expect(pricePresets(undefined, undefined)).toEqual([]);
    expect(pricePresets(1000, 1000)).toEqual([]);
  });
});

describe("sidebarFacets: технические фасеты на широкой категории", () => {
  function facet(code: string, kind: "base" | "tech", counts: number[]): Facet {
    return {
      code,
      label: code,
      type: "checkbox",
      kind,
      options: counts.map((count, i) => ({ value: `v${i}`, label: `v${i}`, count, selected: false })),
    };
  }

  // Числа — «Электроинструмент» со стенда: 1518 товаров, мощность у 518, патрон у 107.
  const broad = () =>
    listing({
      total: 1518,
      facets: [
        navFacet([
          { value: "dreli", label: "Дрели", count: 337 },
          { value: "pily", label: "Пилы", count: 150 },
        ]),
        facet("price", "base", [1518]),
        facet("power", "tech", [300, 218]),
        facet("chuck", "tech", [60, 47]),
      ],
    });

  it("характеристика, покрывающая треть выдачи, показывается", () => {
    expect(sidebarFacets(broad()).map((f) => f.code)).toContain("power");
  });

  // «Энергия удара» относится к 8 % раздела: для остальных 92 % такой фильтр
  // означает «скрыть почти всё».
  it("редкая характеристика на широкой категории остаётся скрытой", () => {
    expect(sidebarFacets(broad()).map((f) => f.code)).not.toContain("chuck");
  });

  it("после выбора типа показываются все характеристики", () => {
    expect(sidebarFacets(broad(), "dreli").map((f) => f.code)).toEqual([
      "price",
      "power",
      "chuck",
    ]);
  });
});

// Диапазонный фасет схлопывает значения в min/max, и count в options не остаётся —
// покрытие приходит отдельным полем из адаптера. На этом «Мощность» (34 % выдачи)
// сначала не попала в сайдбар.
describe("sidebarFacets: покрытие диапазонного фасета", () => {
  const rangeFacet = (code: string, covered: number): Facet => ({
    code,
    label: code,
    type: "range",
    kind: "tech",
    covered,
    min: 100,
    max: 2000,
  });

  const broadWithRanges = () =>
    listing({
      total: 1518,
      facets: [
        navFacet([
          { value: "dreli", label: "Дрели", count: 337 },
          { value: "pily", label: "Пилы", count: 150 },
        ]),
        rangeFacet("attr_power", 518),
        rangeFacet("attr_energy_impact", 131),
      ],
    });

  it("мощность у трети выдачи — показываем", () => {
    expect(sidebarFacets(broadWithRanges()).map((f) => f.code)).toContain("attr_power");
  });

  it("энергия удара у 9 % — скрываем", () => {
    expect(sidebarFacets(broadWithRanges()).map((f) => f.code)).not.toContain(
      "attr_energy_impact",
    );
  });
});
