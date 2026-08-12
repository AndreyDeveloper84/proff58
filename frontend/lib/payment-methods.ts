/**
 * Способы оплаты заказа — один словарь на всю витрину.
 *
 * Раньше названия жили тремя отдельными копиями (checkout, «Спасибо», кабинет).
 * Когда появились наличные и карта при получении, их дописали только в checkout —
 * и на «Спасибо» покупатель увидел сырое «cash», а заказ с картой при получении
 * попал на экран «ожидает оплаты» с кнопкой в кассу. Причина не в трёх опечатках,
 * а в трёх источниках правды, поэтому источник здесь один.
 *
 * Канон — apps/orders/payment_methods.py: сервер решает, что доступно и что
 * принять, витрина только показывает.
 */

export type PaymentMethod = "online" | "invoice" | "cash" | "card_on_pickup";

/** Названия для покупателя. Ключи, кроме канонических, — исторические из старых заказов. */
export const PAYMENT_METHOD_LABELS: Record<string, string> = {
  online: "Онлайн-оплата",
  invoice: "Оплата по счёту",
  cash: "Наличными при получении",
  card_on_pickup: "Картой при получении",
  // Заказы, оформленные до появления канонических кодов.
  card: "Банковская карта",
  yookassa: "Онлайн-оплата",
};

/** Деньги берёт магазин при выдаче — касса сайта не участвует. */
const ON_PICKUP: ReadonlySet<string> = new Set<string>(["cash", "card_on_pickup"]);

/** Платят ли за такой заказ на месте: от этого зависит, предлагать ли оплату онлайн. */
export function isPaidOnPickup(method: string | null | undefined): boolean {
  return ON_PICKUP.has(method ?? "");
}

/** Название способа оплаты; незнакомый код показываем как есть, а не прячем. */
export function paymentMethodLabel(method: string | null | undefined): string {
  if (!method) return "Не указан";
  return PAYMENT_METHOD_LABELS[method] ?? method;
}
