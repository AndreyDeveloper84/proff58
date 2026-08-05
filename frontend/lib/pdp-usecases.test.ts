import { describe, expect, it } from "vitest";

import { DEFAULT_USE_CASES, toolTypeOf, useCasesFor } from "./pdp-usecases";

const withType = (value: string) => [
  { label: "Мощность", value: "800 Вт" },
  { label: "Тип инструмента", value },
];

describe("useCasesFor", () => {
  it("подбирает сценарии по типу инструмента", () => {
    const { cases, isGeneric } = useCasesFor(withType("Перфораторы"));

    expect(isGeneric).toBe(false);
    expect(cases[0].title).toBe("Строительно-монтажные работы");
    expect(cases).toHaveLength(3);
  });

  it("узнаёт болгарку под любым из её имён", () => {
    for (const name of ["Болгарки (УШМ)", "Шлифовальные машины", "УШМ"]) {
      expect(useCasesFor(withType(name)).cases[0].title).toBe("Резка металла");
    }
  });

  // Выдуманное применение в карточке хуже пустого места: по нему покупатель
  // примет решение, а потом вернёт товар.
  it("для незнакомого типа даёт запасной набор, а не выдумку", () => {
    const { cases, isGeneric } = useCasesFor(withType("Ящики для инструмента"));

    expect(isGeneric).toBe(true);
    expect(cases).toEqual(DEFAULT_USE_CASES);
  });

  it("без типа инструмента тоже не гадает", () => {
    expect(useCasesFor([{ label: "Вес", value: "2 кг" }]).isGeneric).toBe(true);
    expect(useCasesFor([]).isGeneric).toBe(true);
  });
});

describe("toolTypeOf", () => {
  it("достаёт тип инструмента из характеристик", () => {
    expect(toolTypeOf(withType("Лобзики"))).toBe("Лобзики");
    expect(toolTypeOf([{ label: "Вес", value: "2 кг" }])).toBeNull();
  });
});
