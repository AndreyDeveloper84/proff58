import { describe, expect, it } from "vitest";

import { isLegalEntityInn, isValidInn, isValidKpp } from "./validation";

// Валидаторы зеркалят серверные _INN_RE/_KPP_RE (apps/orders/invoice.py). Если бэк
// изменит правила — эти тесты фиксируют, что фронт разошёлся с ним.
describe("B2B-реквизиты", () => {
  it("ИНН: 10 цифр (юрлицо) и 12 цифр (ИП) валидны", () => {
    expect(isValidInn("7700000000")).toBe(true);
    expect(isValidInn("770000000000")).toBe(true);
    expect(isValidInn(" 7700000000 ")).toBe(true); // trim
  });

  it("ИНН: другая длина, буквы и пустая строка — невалидны", () => {
    expect(isValidInn("")).toBe(false);
    expect(isValidInn("77000000")).toBe(false);
    expect(isValidInn("77000000000")).toBe(false); // 11 цифр
    expect(isValidInn("77000000AB")).toBe(false);
  });

  it("юрлицо определяется по ИНН из 10 цифр (у ИП — 12, КПП не требуется)", () => {
    expect(isLegalEntityInn("7700000000")).toBe(true);
    expect(isLegalEntityInn("770000000000")).toBe(false);
    expect(isLegalEntityInn("")).toBe(false);
  });

  it("КПП: ровно 9 цифр", () => {
    expect(isValidKpp("770001001")).toBe(true);
    expect(isValidKpp("77000100")).toBe(false);
    expect(isValidKpp("7700010012")).toBe(false);
    expect(isValidKpp("")).toBe(false);
  });
});
