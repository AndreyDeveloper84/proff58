// Семантика статусов заказа для UI — по машиночитаемой оси fulfillment_status
// (apps/orders/models.py: FulfillmentStatus), а не по разбору русского текста.
//
// Раньше страницы кабинета парсили display_status подстроками ("достав", "сбор"…) —
// и расходились между собой: «В доставке» на профиле считался «в обработке», в списке
// заказов попадал во вкладку «Доставленные» с зелёным бейджем и кнопкой «Повторить
// заказ», а «Собирается»/«Готов к выдаче»/«Новый»/«Ожидает оплаты» получали серый
// дефолт (токен "сбор" не совпадает с «Собирается», "доставлен" — ни с одной строкой
// бэка). display_status — только человекочитаемый текст бейджа; решения — здесь.

import type { FulfillmentStatus, Order } from "./types";

// Терминальные отмены/возвраты видны по display_status? Нет — по осям. Отмена живёт в
// fulfillment_status=cancelled; возвраты — в payment_status (refunded/partially_refunded).
export function isCancelled(order: Order): boolean {
  return (
    order.fulfillment_status === "cancelled" ||
    order.payment_status === "expired" ||
    order.payment_status === "refunded"
  );
}

export function isDelivered(order: Order): boolean {
  return order.fulfillment_status === "completed" && !isCancelled(order);
}

// «В обработке» = живой заказ, ещё не выданный покупателю. shipped («В доставке») —
// тоже в обработке: заказ ещё едет.
export function isInProgress(order: Order): boolean {
  return !isDelivered(order) && !isCancelled(order);
}

// Классы бейджа по оси обработки. Exhaustive switch: добавление нового значения
// FulfillmentStatus на бэке даст ошибку компиляции здесь, а не серый бейдж в проде.
export function statusBadgeClass(order: Order): string {
  if (isCancelled(order)) return "bg-red-50 text-danger";
  if (order.payment_status === "pending" && order.fulfillment_status === "new") {
    return "bg-amber-50 text-amber-700"; // ждём оплату — предупреждающий
  }
  const status: FulfillmentStatus = order.fulfillment_status;
  switch (status) {
    case "new":
    case "confirmed":
    case "assembling":
      return "bg-blue-50 text-blue-700";
    case "ready":
      return "bg-accent/10 text-accent"; // требует действия покупателя — выделяем
    case "shipped":
      return "bg-blue-50 text-blue-700"; // ещё едет — НЕ зелёный «выполнен»
    case "completed":
      return "bg-accent/10 text-accent";
    case "cancelled":
      return "bg-red-50 text-danger"; // недостижимо (isCancelled выше), для полноты switch
    default: {
      // Компилятор гарантирует полноту: сюда можно попасть только при рассинхроне с бэком.
      const _exhaustive: never = status;
      void _exhaustive;
      return "bg-raised text-ink-2";
    }
  }
}
