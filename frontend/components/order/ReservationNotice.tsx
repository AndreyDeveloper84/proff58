"use client";

import { useEffect, useState } from "react";
import { Clock3 } from "lucide-react";
import type { Order } from "@/lib/types";

// Плашка резерва товара для B2C (#568): «зарезервировано до HH:MM» либо
// expired-состояние. Живого MM:SS-тикера нет намеренно: честный признак
// истечения даёт сервер (reservation_expired), клиентский interval лишь
// переключает плашку, если срок наступил, пока страница открыта.
const RECHECK_MS = 30_000;

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ReservationNotice({ order }: { order: Order }) {
  const { reserved_until, reservation_status, reservation_expired } = order;
  const untilMs = reserved_until ? new Date(reserved_until).getTime() : null;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!untilMs || Date.now() >= untilMs) return;
    const id = setInterval(() => setNow(Date.now()), RECHECK_MS);
    return () => clearInterval(id);
  }, [untilMs]);

  // B2B видит эквивалент в счёте (24ч); у отменённого заказа payment остаётся
  // pending — без проверки fulfillment плашка «истёк» показалась бы на отмене.
  if (order.customer_type !== "b2c") return null;
  if (order.payment_status !== "pending") return null;
  if (order.fulfillment_status === "cancelled") return null;
  if (!reserved_until || !untilMs) return null;
  if (reservation_status !== "held" && reservation_status !== "released") return null;

  const expired = reservation_expired === true || now >= untilMs;

  if (expired) {
    return (
      <p className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
        Время резерва истекло {formatDateTime(reserved_until)}: товар возвращён в свободную
        продажу. Наличие подтвердит менеджер при обработке заказа.
      </p>
    );
  }

  if (reservation_status !== "held") return null;

  return (
    <p className="flex items-center gap-1.5 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
      <Clock3 className="h-4 w-4 shrink-0" aria-hidden />
      Товар зарезервирован за вами до {formatDateTime(reserved_until)}.
    </p>
  );
}
