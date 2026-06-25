// Оформление заказа через same-origin BFF (#246).
import { apiFetch } from "./api";
import type { Order, PlaceOrderData } from "./types";

/**
 * Оформить заказ из активной корзины (POST /api/orders/). Возвращает снимок заказа —
 * его и показываем на /thanks (GET по номеру гостю недоступен, IsAuthenticated).
 */
export function placeOrder(data: PlaceOrderData): Promise<Order> {
  // Без хвостового слэша (см. lib/cart.ts) — route handler проксирует в Django /api/orders/.
  return apiFetch<Order>("/api/orders", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
