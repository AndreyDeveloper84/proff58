import { describe, expect, it } from "vitest";

import { isPaidOnPickup, paymentMethodLabel } from "./payment-methods";

describe("названия способов оплаты", () => {
  it("канонические коды показывает по-человечески", () => {
    expect(paymentMethodLabel("online")).toBe("Онлайн-оплата");
    expect(paymentMethodLabel("invoice")).toBe("Оплата по счёту");
    expect(paymentMethodLabel("cash")).toBe("Наличными при получении");
    expect(paymentMethodLabel("card_on_pickup")).toBe("Картой при получении");
  });

  it("понимает коды из старых заказов", () => {
    expect(paymentMethodLabel("yookassa")).toBe("Онлайн-оплата");
    expect(paymentMethodLabel("card")).toBe("Банковская карта");
  });

  // Показать сырой код неприятно, но честно: молчание скрыло бы, что заказ
  // оформлен способом, о котором витрина не знает.
  it("незнакомый код показывает как есть, пустой — «Не указан»", () => {
    expect(paymentMethodLabel("sbp")).toBe("sbp");
    expect(paymentMethodLabel("")).toBe("Не указан");
    expect(paymentMethodLabel(null)).toBe("Не указан");
  });
});

describe("оплата на месте", () => {
  it("наличные и карта на выдаче — оплата в магазине", () => {
    expect(isPaidOnPickup("cash")).toBe(true);
    expect(isPaidOnPickup("card_on_pickup")).toBe(true);
  });

  it("онлайн и счёт — не оплата на месте", () => {
    expect(isPaidOnPickup("online")).toBe(false);
    expect(isPaidOnPickup("invoice")).toBe(false);
    expect(isPaidOnPickup(undefined)).toBe(false);
  });
});
