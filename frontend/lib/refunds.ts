// Заявка покупателя на возврат денег за оплаченный онлайн заказ.
// Правила (сроки, одна открытая заявка) решает сервер: интерфейс рисует блок по
// ответу и показывает текст отказа как есть.
import { apiFetch } from "@/lib/api";

export type RefundRequestStatus =
  "pending" | "processing" | "refunded" | "rejected";

export type RefundRequestItem = {
  id: number;
  status: RefundRequestStatus;
  status_label: string;
  reason: string;
  reason_label: string;
  comment: string;
  /** Сколько вернули; null — пока не вернули. */
  amount: string | null;
  /** Ответ менеджера (причина отказа). */
  decision_comment: string;
  created_at: string;
  decided_at: string | null;
};

export type RefundState = {
  can_request: boolean;
  /** Почему нельзя подать заявку; null — объяснять нечего (заказ не оплачен онлайн). */
  block_reason: string | null;
  /** До какого момента принимается заявка; null — пока заказ не получен. */
  deadline: string | null;
  reasons: { value: string; label: string }[];
  requests: RefundRequestItem[];
};

function refundPath(orderNumber: string) {
  return `/api/orders/${encodeURIComponent(orderNumber)}/refund-request`;
}

export async function getRefundState(
  orderNumber: string,
): Promise<RefundState> {
  return apiFetch<RefundState>(refundPath(orderNumber), { method: "GET" });
}

export async function requestRefund(
  orderNumber: string,
  reason: string,
  comment: string,
): Promise<RefundState> {
  return apiFetch<RefundState>(refundPath(orderNumber), {
    method: "POST",
    body: JSON.stringify({ reason, comment }),
  });
}
