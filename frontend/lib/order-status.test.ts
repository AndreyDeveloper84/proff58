import { describe, expect, it } from "vitest";

import { isCancelled, isDelivered, isInProgress, statusBadgeClass } from "./order-status";
import type { FulfillmentStatus, Order, OrderPaymentStatus } from "./types";

function makeOrder(
  fulfillment: FulfillmentStatus,
  payment: OrderPaymentStatus = "paid",
): Order {
  return {
    fulfillment_status: fulfillment,
    payment_status: payment,
    display_status: "не используется логикой",
  } as Order;
}

describe("order-status: семантика по машиночитаемым осям", () => {
  it("«В доставке» (shipped) — ещё В ОБРАБОТКЕ, а не доставлен", () => {
    // Регрессия: раньше страницы матчили подстроку "достав" в display_status,
    // и «В доставке» попадал во вкладку «Доставленные» с кнопкой «Повторить заказ»,
    // а счётчик профиля одновременно считал его «в обработке».
    const shipped = makeOrder("shipped");
    expect(isInProgress(shipped)).toBe(true);
    expect(isDelivered(shipped)).toBe(false);
    expect(isCancelled(shipped)).toBe(false);
  });

  it("completed — доставлен; new/confirmed/assembling/ready — в обработке", () => {
    expect(isDelivered(makeOrder("completed"))).toBe(true);
    for (const s of ["new", "confirmed", "assembling", "ready"] as const) {
      expect(isInProgress(makeOrder(s))).toBe(true);
      expect(isDelivered(makeOrder(s))).toBe(false);
    }
  });

  it("отмена и возвраты — терминальные", () => {
    expect(isCancelled(makeOrder("cancelled"))).toBe(true);
    expect(isCancelled(makeOrder("new", "expired"))).toBe(true);
    expect(isCancelled(makeOrder("completed", "refunded"))).toBe(true);
    // Частичный возврат заказ НЕ отменяет.
    expect(isCancelled(makeOrder("completed", "partially_refunded"))).toBe(false);
  });

  it("каждый статус обработки получает содержательный бейдж (не серый дефолт)", () => {
    // Регрессия: «Собирается»/«Готов к выдаче»/«Новый»/«Ожидает оплаты» падали в серый
    // дефолт (мёртвые токены "сбор"/"доставлен"), а «В доставке» красился как «выполнен».
    const GRAY = "bg-raised text-ink-2";
    const all: FulfillmentStatus[] = [
      "new",
      "confirmed",
      "assembling",
      "ready",
      "shipped",
      "completed",
      "cancelled",
    ];
    for (const s of all) {
      expect(statusBadgeClass(makeOrder(s)), `статус ${s}`).not.toBe(GRAY);
    }
    // «В доставке» — синий (в пути), НЕ зелёный как завершённый.
    expect(statusBadgeClass(makeOrder("shipped"))).toBe("bg-blue-50 text-blue-700");
    // «Готов к выдаче» — выделен (требует действия покупателя).
    expect(statusBadgeClass(makeOrder("ready"))).toBe("bg-accent/10 text-accent");
    // «Ожидает оплаты» — предупреждающий.
    expect(statusBadgeClass(makeOrder("new", "pending"))).toBe("bg-amber-50 text-amber-700");
  });
});
