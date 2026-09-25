// Передача снимка заказа со страницы checkout на /thanks через sessionStorage (#246).
// Почему не GET /api/orders/{number}/: он IsAuthenticated — гостю недоступен. Поэтому
// показываем заказ из ответа POST /api/orders/. sessionStorage переживает client-навигацию
// и закрывается с вкладкой (ПДн не оседают надолго). На /thanks есть fallback, если пусто.
import type { Order } from "./types";

const PREFIX = "order:";

/** Сохранить снимок заказа под его номером (вызывается на checkout после успешного POST). */
export function stashOrder(order: Order): void {
  try {
    sessionStorage.setItem(`${PREFIX}${order.order_number}`, JSON.stringify(order));
  } catch {
    // sessionStorage недоступен (private mode/квота) — /thanks отрендерит fallback по номеру.
  }
}

/** Прочитать снимок заказа по номеру (на /thanks). null, если нет/повреждён. */
export function readStashedOrder(orderNumber: string): Order | null {
  try {
    const raw = sessionStorage.getItem(`${PREFIX}${orderNumber}`);
    return raw ? (JSON.parse(raw) as Order) : null;
  } catch {
    return null;
  }
}
