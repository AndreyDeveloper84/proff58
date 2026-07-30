import { beforeEach, describe, expect, it } from "vitest";

import {
  COMPARE_LIMIT,
  COMPARE_STORAGE_KEY,
  clearCompare,
  removeFromCompare,
  toggleCompare,
} from "./compare";

function stored(): string[] {
  return JSON.parse(localStorage.getItem(COMPARE_STORAGE_KEY) ?? "[]");
}

describe("список сравнения", () => {
  beforeEach(() => {
    localStorage.clear();
    clearCompare();
  });

  it("добавляет и убирает товар одним и тем же действием", () => {
    toggleCompare("perforator-bosch");
    expect(stored()).toEqual(["perforator-bosch"]);

    toggleCompare("perforator-bosch");
    expect(stored()).toEqual([]);
  });

  it("сохраняет порядок добавления", () => {
    toggleCompare("a");
    toggleCompare("b");
    toggleCompare("c");
    expect(stored()).toEqual(["a", "b", "c"]);
  });

  // Пятая колонка не влезает на экран, и таблица начинает прокручиваться вбок —
  // сравнивать в ней уже нельзя. Отказ должен быть виден вызывающему, чтобы
  // кнопка объяснила человеку, почему ничего не произошло.
  it("не берёт больше лимита и сообщает об отказе", () => {
    for (let i = 0; i < COMPARE_LIMIT; i++) {
      expect(toggleCompare(`tovar-${i}`)).toBe(true);
    }
    expect(toggleCompare("лишний")).toBe(false);
    expect(stored()).toHaveLength(COMPARE_LIMIT);
    expect(stored()).not.toContain("лишний");
  });

  // Упёршись в лимит, убрать уже выбранное всё равно можно — иначе список
  // становится ловушкой.
  it("удаление работает и на заполненном списке", () => {
    for (let i = 0; i < COMPARE_LIMIT; i++) toggleCompare(`tovar-${i}`);

    expect(toggleCompare("tovar-0")).toBe(true);
    expect(stored()).not.toContain("tovar-0");
    expect(toggleCompare("новый")).toBe(true);
  });

  it("removeFromCompare убирает точечно, clearCompare — всё", () => {
    toggleCompare("a");
    toggleCompare("b");

    removeFromCompare("a");
    expect(stored()).toEqual(["b"]);

    clearCompare();
    expect(stored()).toEqual([]);
  });

  // В localStorage могло остаться что угодно от прошлых версий или чужого кода:
  // страница сравнения не должна падать на разборе.
  it("переживает мусор в localStorage", () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, "{не json");
    expect(() => toggleCompare("a")).not.toThrow();
    expect(stored()).toEqual(["a"]);

    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["ok", 42, null]));
    toggleCompare("b");
    expect(stored()).toEqual(["ok", "b"]);
  });
});
