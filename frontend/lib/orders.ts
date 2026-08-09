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

/** Ответ кассы: куда вести покупателя и в каком состоянии оплата заказа. */
export type PaymentStart = {
  payment_status: string;
  confirmation_url: string;
  provider_status?: string;
};

/**
 * Получить ссылку на оплату заказа (POST /api/orders/{number}/pay).
 *
 * Идемпотентно: повторный вызов возвращает ту же ссылку, а не новый платёж, —
 * поэтому этой же функцией работает и «Повторить оплату» на странице заказа.
 * Ошибки кассы (503) прилетают как ApiError и НЕ означают потерю заказа: он уже
 * оформлен, оплату можно начать позже.
 */
export function startOrderPayment(orderNumber: string, accessToken?: string): Promise<PaymentStart> {
  const query = accessToken ? `?t=${encodeURIComponent(accessToken)}` : "";
  return apiFetch<PaymentStart>(`/api/orders/${encodeURIComponent(orderNumber)}/pay${query}`, {
    method: "POST",
  });
}

/** Свежий гостевой заказ по номеру и токену — для проверки состояния оплаты. */
export function getGuestOrder(orderNumber: string, accessToken: string): Promise<Order> {
  return apiFetch<Order>(
    `/api/orders/${encodeURIComponent(orderNumber)}/guest?t=${encodeURIComponent(accessToken)}`,
  );
}
