import { describe, expect, it } from "vitest";

import { allTypesLabel, categoryGenitive, popularTypesTitle } from "./category-phrases";

describe("родительный падеж раздела", () => {
  it("знает корневые разделы каталога", () => {
    expect(categoryGenitive("Электроинструмент")).toBe("электроинструмента");
    expect(categoryGenitive("Ручной инструмент")).toBe("ручного инструмента");
    expect(categoryGenitive("Садовая техника и инвентарь")).toBe("садовой техники");
    expect(categoryGenitive("Сварочное оборудование")).toBe("сварочного оборудования");
  });

  it("узнаёт раздел независимо от регистра", () => {
    expect(categoryGenitive("ЭЛЕКТРОИНСТРУМЕНТ")).toBe("электроинструмента");
  });

  // Дерево каталога растёт на бэкенде, и незнакомое имя не должно ломать страницу.
  it("незнакомый раздел — null, а не выдумка", () => {
    expect(categoryGenitive("Батискафы")).toBeNull();
    expect(categoryGenitive("")).toBeNull();
  });
});

describe("подписи", () => {
  it("строят фразу из падежа", () => {
    expect(allTypesLabel("Электроинструмент")).toBe("Все виды электроинструмента");
    expect(popularTypesTitle("Электроинструмент")).toBe("Популярные виды электроинструмента");
  });

  it("для незнакомого раздела короче, но не врут", () => {
    expect(allTypesLabel("Батискафы")).toBe("Все виды");
    expect(popularTypesTitle("Батискафы")).toBe("Популярные виды");
  });
});
