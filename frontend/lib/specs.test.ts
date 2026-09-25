import { describe, expect, it } from "vitest";

import { apiProductToProduct, formatSpecValue } from "./adapters";
import { hasRealSpecs, keySpecs } from "./specs";

// DATA-01: характеристики — пары «Название: значение» в порядке backend.
const api = (attributes: unknown[]) =>
  apiProductToProduct({ id: 1, name: "Перфоратор", slug: "perf", attributes } as never);

describe("характеристики товара (DATA-01)", () => {
  it("порядок backend сохраняется, витрина ничего не пересортировывает", () => {
    const product = api([
      { name: "Энергия удара", slug: "energy_impact", unit: "Дж", value: 2.7 },
      { name: "Мощность", slug: "power", unit: "Вт", value: 800 },
      { name: "АКБ в комплекте", slug: "battery_included", unit: "", value: false },
    ]);

    expect(product.specs.map((s) => `${s.label}: ${s.value}`)).toEqual([
      "Энергия удара: 2,7 Дж",
      "Мощность: 800 Вт",
      "АКБ в комплекте: Нет",
    ]);
  });

  it("ноль и «Нет» не исчезают как ложные значения", () => {
    const product = api([
      { name: "Реверс", slug: "reverse", value: false },
      { name: "Люфт", slug: "play", unit: "мм", value: 0 },
    ]);

    expect(product.specs.map((s) => s.value)).toEqual(["Нет", "0 мм"]);
  });

  it("пустые значения и подписи строк не создают", () => {
    const product = api([
      { name: "Мощность", slug: "power", unit: "Вт", value: null },
      { name: "Патрон", slug: "chuck", value: "   " },
      { name: "Страна", slug: "country", value: "" },
      { name: "  ", slug: "junk", value: "x" },
      { name: "Напряжение", slug: "voltage", unit: "В", value: 18 },
    ]);

    expect(product.specs).toEqual([{ label: "Напряжение", value: "18 В", slug: "voltage" }]);
  });

  it("единица не повторяется и не теряется из-за случайной буквы в значении", () => {
    expect(formatSpecValue("220 В", "В")).toBe("220 В");
    expect(formatSpecValue("220в", "В")).toBe("220в");
    // Раньше проверка была «значение содержит единицу»: буква «м» в слове съедала «м».
    expect(formatSpecValue("сталь матовая", "м")).toBe("сталь матовая м");
    expect(formatSpecValue(12.5, "мм")).toBe("12,5 мм");
    expect(formatSpecValue("   ", "Вт")).toBe("");
  });

  it("одна и та же строка дважды — один раз", () => {
    const product = api([
      { name: "Диаметр", slug: "diameter", unit: "мм", value: 125 },
      { name: "Диаметр", slug: "disc_diameter", unit: "мм", value: 125 },
      { name: "Диаметр", slug: "bore", unit: "мм", value: 22.2 },
    ]);

    expect(product.specs.map((s) => s.value)).toEqual(["125 мм", "22,2 мм"]);
  });

  it("карточка берёт первые ключевые; тип инструмента и неключевые пропускает", () => {
    const specs = [
      { label: "Тип инструмента", value: "Перфораторы", slug: "tool_type" },
      { label: "Энергия удара", value: "2,7 Дж", slug: "energy_impact", isKey: true },
      { label: "Страна", value: "Германия", slug: "country", isKey: false },
      { label: "Мощность", value: "800 Вт", slug: "power", isKey: true },
      { label: "Патрон", value: "SDS-plus", slug: "chuck" },
    ];

    expect(keySpecs(specs, 2).map((s) => s.label)).toEqual(["Энергия удара", "Мощность"]);
    expect(keySpecs(specs, 10).map((s) => s.label)).toEqual(["Энергия удара", "Мощность", "Патрон"]);
  });

  it("товар только с типом инструмента — без характеристик", () => {
    expect(hasRealSpecs([{ label: "Тип инструмента", value: "Газонокосилки" }])).toBe(false);
    expect(hasRealSpecs(undefined)).toBe(false);
    expect(keySpecs(undefined, 3)).toEqual([]);
  });
});
