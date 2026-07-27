import { describe, expect, it } from "vitest";

import {
  formatDate,
  formatDateTime,
  formatDeliverySlot,
  formatPrice,
  formatSlotDay,
  pluralize,
} from "./format";

// #574: цена и даты форматируются в одном месте — до этого каждая страница
// объявляла свой хелпер, и один и тот же заказ/отзыв выглядел по-разному.
describe("formatPrice", () => {
  it("рубли по умолчанию, без копеек", () => {
    // NBSP/узкие пробелы у Intl зависят от ICU — сверяем по подстрокам.
    const s = formatPrice(1234);
    expect(s).toContain("₽");
    expect(s.replace(/\s/g, "")).toContain("1234");
  });

  it("уважает переданную валюту (не всегда «₽»)", () => {
    const s = formatPrice(1000, "USD");
    expect(s).not.toContain("₽");
    expect(s).toContain("$");
  });
});

describe("даты", () => {
  it("formatDate — DD.MM.YYYY", () => {
    expect(formatDate("2026-07-21T10:00:00+03:00")).toMatch(/^\d{2}\.\d{2}\.\d{4}$/);
  });

  it("formatDateTime — дата и время", () => {
    expect(formatDateTime("2026-07-21T10:00:00+03:00")).toMatch(
      /^\d{2}\.\d{2}\.\d{4},\s\d{2}:\d{2}$/,
    );
  });

  it("formatSlotDay — день недели и месяц словом", () => {
    const s = formatSlotDay("2026-07-21");
    expect(s).toContain("21");
    expect(s).toContain("июля");
  });

  it("formatDeliverySlot — дата и интервал", () => {
    expect(formatDeliverySlot({ date: "2026-07-21", starts_at: "10:00", ends_at: "14:00" })).toBe(
      "21.07.2026, 10:00–14:00",
    );
  });
});

// Русская множественная форма для счётчиков («126 товаров», «1 товар», «22 товара»).
describe("pluralize", () => {
  const форма = (n: number) => pluralize(n, "товар", "товара", "товаров");

  it("one: 1, 21, 31", () => {
    expect(форма(1)).toBe("товар");
    expect(форма(21)).toBe("товар");
    expect(форма(31)).toBe("товар");
  });

  it("few: 2–4, 22–24", () => {
    expect(форма(2)).toBe("товара");
    expect(форма(4)).toBe("товара");
    expect(форма(23)).toBe("товара");
  });

  it("many: 0, 5–20, 25, 100", () => {
    expect(форма(0)).toBe("товаров");
    expect(форма(5)).toBe("товаров");
    expect(форма(11)).toBe("товаров");
    expect(форма(14)).toBe("товаров");
    expect(форма(25)).toBe("товаров");
    expect(форма(100)).toBe("товаров");
  });
});
