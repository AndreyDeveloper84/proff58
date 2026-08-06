import { describe, expect, it } from "vitest";
import { groupProductSpecs, hasPassportSpecs, selectKeySpecs } from "./ProductDetailsShowcase";

const specs = [
  { label: "Тип инструмента", value: "Перфораторы" },
  { label: "Мощность", value: "800 Вт" },
  { label: "Питание", value: "Сеть" },
  { label: "Энергия удара", value: "3 Дж" },
  { label: "Тип патрона", value: "SDS-plus" },
  { label: "Режимы работы", value: "3" },
  { label: "Вес", value: "2,7 кг" },
];

describe("ProductDetailsShowcase", () => {
  it("выбирает четыре ключевых параметра в полезном порядке", () => {
    expect(selectKeySpecs(specs)).toEqual([
      { label: "Мощность", value: "800 Вт" },
      { label: "Энергия удара", value: "3 Дж" },
      { label: "Тип патрона", value: "SDS-plus" },
      { label: "Режимы работы", value: "3" },
    ]);
  });

  it("раскладывает характеристики по разделам технического паспорта", () => {
    const groups = groupProductSpecs(specs);

    expect(groups.map((group) => group.title)).toEqual([
      "Производительность",
      "Оснастка",
      "Питание и корпус",
      "Дополнительно",
    ]);
    expect(groups[0].specs.map((spec) => spec.label)).toEqual(["Мощность", "Энергия удара"]);
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
