import { beforeEach, describe, expect, it, vi } from "vitest";

import { subscribeActionSuccess } from "./action-feedback";

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

// Столбики в шапке отыгрывают только реальное добавление: удаление, отказ по
// лимиту и очистка списка счётчик меняют, но «успешным добавлением» не являются.
describe("список сравнения → шина действий", () => {
  it("издаёт событие при добавлении и молчит при удалении, лимите и очистке", () => {
    localStorage.clear();
    clearCompare();
    const listener = vi.fn();
    const unsubscribe = subscribeActionSuccess(listener);
    try {
      toggleCompare("a");
      expect(listener).toHaveBeenCalledTimes(1);
      expect(listener).toHaveBeenLastCalledWith("compare");

      toggleCompare("a"); // удаление
      expect(listener).toHaveBeenCalledTimes(1);

      for (let i = 0; i < COMPARE_LIMIT; i++) toggleCompare(`p${i}`);
      expect(listener).toHaveBeenCalledTimes(1 + COMPARE_LIMIT);
      expect(toggleCompare("лишний")).toBe(false); // лимит
      expect(listener).toHaveBeenCalledTimes(1 + COMPARE_LIMIT);

      removeFromCompare("p0");
      clearCompare();
      expect(listener).toHaveBeenCalledTimes(1 + COMPARE_LIMIT);
    } finally {
      unsubscribe();
    }
  });
});
