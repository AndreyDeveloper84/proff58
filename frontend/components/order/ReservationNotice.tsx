"use client";

import { useEffect, useState } from "react";
import { Clock3 } from "lucide-react";
import { formatDateTime } from "@/lib/format";
import type { Order } from "@/lib/types";

// Плашка резерва товара для B2C (#568): «зарезервировано до HH:MM» либо
// expired-состояние. Живого MM:SS-тикера нет намеренно: честный признак
// истечения даёт сервер (reservation_expired), клиентский interval лишь
// переключает плашку, если срок наступил, пока страница открыта.
const RECHECK_MS = 30_000;

/** Состояние резерва заказа. "none" — показывать нечего. */
export type ReservationState = "none" | "held" | "expired";

/**
 * #574: видимость резерва вынесена из компонента, чтобы список заказов мог
 * показать ту же информацию компактно, не дублируя правила (B2B видит резерв
 * в счёте, у отменённого заказа payment остаётся pending и т.д.).
 */
export function reservationState(order: Order, nowMs: number = Date.now()): ReservationState {
  const { reserved_until, reservation_status, reservation_expired } = order;
  if (order.customer_type !== "b2c") return "none";
  if (order.payment_status !== "pending") return "none";
  if (order.fulfillment_status === "cancelled") return "none";
  if (!reserved_until) return "none";
  const untilMs = new Date(reserved_until).getTime();
  if (!untilMs) return "none";
  if (reservation_status !== "held" && reservation_status !== "released") return "none";
  if (reservation_expired === true || nowMs >= untilMs) return "expired";
  return reservation_status === "held" ? "held" : "none";
}

export function ReservationNotice({ order }: { order: Order }) {
  const untilMs = order.reserved_until ? new Date(order.reserved_until).getTime() : null;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!untilMs || Date.now() >= untilMs) return;
    const id = setInterval(() => setNow(Date.now()), RECHECK_MS);
    return () => clearInterval(id);
  }, [untilMs]);

  const state = reservationState(order, now);
  if (state === "none") return null;

  // aria-live: смена «зарезервирован» → «время истекло» происходит без действия
  // пользователя, о ней нужно сообщить (docs/design/pages/checkout.md §7).
  if (state === "expired") {
    return (
      <p
        aria-live="polite"
        className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
      >
        Время резерва истекло {formatDateTime(order.reserved_until!)}: товар возвращён в
        свободную продажу. Наличие подтвердит менеджер при обработке заказа.
      </p>
    );
  }

  return (
    <p
      aria-live="polite"
      className="flex items-center gap-1.5 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700"
    >
      <Clock3 className="h-4 w-4 shrink-0" aria-hidden />
      Товар зарезервирован за вами до {formatDateTime(order.reserved_until!)}.
    </p>
  );
}
