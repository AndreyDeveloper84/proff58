"use client";

import { useState } from "react";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { startOrderPayment } from "@/lib/orders";

/**
 * Кнопка «Оплатить заказ» с обработкой ответа кассы. Одна на страницу «Спасибо»
 * и на карточку заказа в кабинете: покупатель, закрывший страницу до оплаты,
 * раньше не мог вернуться к ней иначе как из истории браузера.
 *
 * accessToken — только для гостя (владелец оплачивает по сессии). Ошибка кассы
 * или 409 «доставка уточняется» показываются текстом, заказ никуда не девается.
 */
export function PayOrderButton({
  orderNumber,
  accessToken,
  className,
}: {
  orderNumber: string;
  accessToken?: string;
  className?: string;
}) {
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pay = async () => {
    if (paying) return;
    setPaying(true);
    setError(null);
    try {
      const started = await startOrderPayment(orderNumber, accessToken);
      if (started.confirmation_url) {
        window.location.assign(started.confirmation_url);
        return;
      }
      // Ссылки нет — значит заказ уже оплачен; покажем это без перезагрузки страницы.
      window.location.reload();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Не удалось перейти к оплате. Заказ сохранён — попробуйте позже.",
      );
      setPaying(false);
    }
  };

  return (
    <div className={className}>
      <Button variant="accent" onClick={pay} disabled={paying}>
        {paying ? "Переходим к оплате…" : "Оплатить заказ"}
      </Button>
      {error && (
        <p role="alert" className="mt-2 flex items-start gap-2 text-sm text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {error}
        </p>
      )}
    </div>
  );
}

/** Можно ли предлагать оплату: онлайн, ещё не оплачен, не отменён и доставка рассчитана. */
export function canPayOnline(order: {
  payment_method: string;
  payment_status: string;
  fulfillment_status: string;
  delivery_calc_status: string;
}): boolean {
  return (
    order.payment_method === "online" &&
    order.payment_status === "pending" &&
    order.fulfillment_status !== "cancelled" &&
    order.delivery_calc_status !== "manual_required"
  );
}
