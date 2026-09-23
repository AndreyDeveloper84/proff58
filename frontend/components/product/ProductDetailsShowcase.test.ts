import { describe, expect, it } from "vitest";
import { groupProductSpecs } from "@/lib/spec-groups";
import { hasPassportSpecs, selectKeySpecs } from "./ProductDetailsShowcase";

// Порядок — как его отдаёт detail-эндпоинт (DATA-01): ключевые по типу товара, затем
// остальные, служебный тип инструмента — последним.
const specs = [
  { label: "Энергия удара", value: "3 Дж", slug: "energy_impact", isKey: true },
  { label: "Мощность", value: "800 Вт", slug: "power", isKey: true },
  { label: "Тип патрона", value: "SDS-plus", slug: "chuck", isKey: true },
  { label: "Питание", value: "Сеть", slug: "power_source", isKey: true },
  { label: "Вес", value: "2,7 кг", slug: "weight_kg", isKey: true },
  { label: "Режимы работы", value: "3", slug: "modes", isKey: false },
  { label: "Тип инструмента", value: "Перфораторы", slug: "tool_type", isKey: true },
];

describe("ProductDetailsShowcase", () => {
  it("«Главное в работе» берёт порядок backend, а не угадывает по подписям", () => {
    expect(selectKeySpecs(specs).map((spec) => spec.label)).toEqual([
      "Энергия удара",
      "Мощность",
      "Тип патрона",
      "Питание",
    ]);
  });

  it("неключевые характеристики и тип инструмента в «главное» не попадают", () => {
    const labels = selectKeySpecs(specs, 10).map((spec) => spec.label);
    expect(labels).not.toContain("Режимы работы");
    expect(labels).not.toContain("Тип инструмента");
  });

  it("раскладывает характеристики по разделам технического паспорта", () => {
    const groups = groupProductSpecs(specs);

    expect(groups.map((group) => group.title)).toEqual([
      "Производительность",
      "Оснастка",
      "Питание и корпус",
      "Дополнительно",
    ]);
    expect(groups[0].specs.map((spec) => spec.label)).toEqual(["Энергия удара", "Мощность"]);
    expect(groups[1].specs.map((spec) => spec.label)).toEqual(["Тип патрона", "Режимы работы"]);
    expect(groups[2].specs.map((spec) => spec.label)).toEqual(["Питание", "Вес"]);
    expect(groups[3].specs.map((spec) => spec.label)).toEqual(["Тип инструмента"]);
  });

  it("не оставляет пустые группы", () => {
    expect(groupProductSpecs([{ label: "Цвет", value: "Зелёный" }])).toHaveLength(1);
  });
});

describe("наполнение карточки", () => {
  // 12 250 товаров каталога имеют единственную «характеристику» — тип инструмента.
  // Это служебная строка разбора, а не паспорт: таблица из неё одной читалась как
  // обрезанная.
  it("считает паспорт пустым, когда есть только тип инструмента", () => {
    expect(hasPassportSpecs([{ label: "Тип инструмента", value: "Газонокосилки" }])).toBe(false);
    expect(hasPassportSpecs([])).toBe(false);
  });

  it("видит паспорт при любой настоящей характеристике", () => {
    expect(
      hasPassportSpecs([
        { label: "Тип инструмента", value: "Перфораторы" },
        { label: "Мощность", value: "950 Вт" },
      ]),
    ).toBe(true);
  });
});
