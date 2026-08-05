"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle, Clock, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { startOrderPayment } from "@/lib/orders";
import { formatPrice } from "@/lib/format";
import type { Order } from "@/lib/types";

/**
 * Итог оформления: что именно произошло с заказом и что делать дальше.
 *
 * Раньше страница «Спасибо» всегда сообщала об успехе — сразу после создания
 * заказа, ещё до всякой оплаты. Для заказа с онлайн-оплатой это неправда: пока
 * касса не подтвердила платёж, заказ оформлен, но не оплачен, и человеку нужно
 * не поздравление, а кнопка «Оплатить».
 *
 * Состояний четыре, и они читаются по двум полям заказа: способу оплаты и
 * статусу платежа. Ничего не додумываем — если сервер говорит «ожидает», так и
 * пишем.
 */
type Outcome = "paid" | "awaiting-payment" | "invoice" | "on-delivery";

function outcomeOf(order: Order): Outcome {
  if (order.payment_method === "invoice") return "invoice";
  if (order.payment_method === "cash") return "on-delivery";
  return order.payment_status === "paid" ? "paid" : "awaiting-payment";
}

const VIEWS: Record<
  Outcome,
  { icon: typeof CheckCircle; tone: string; title: string; text: string }
> = {
  paid: {
    icon: CheckCircle,
    tone: "text-accent",
    title: "Заказ оплачен",
    text: "Платёж подтверждён. Мы начали собирать заказ и сообщим об изменении статуса.",
  },
  "awaiting-payment": {
    icon: Clock,
    tone: "text-hit",
    title: "Заказ оформлен, ожидает оплаты",
    text: "Заказ сохранён и никуда не денется. Оплатите его, чтобы мы начали сборку.",
  },
  invoice: {
    icon: FileText,
    tone: "text-info",
    title: "Счёт сформирован",
    text: "Заказ принят. Счёт доступен в личном кабинете — после оплаты мы начнём сборку.",
  },
  "on-delivery": {
    icon: CheckCircle,
    tone: "text-accent",
    title: "Заказ принят",
    text: "Оплата при получении. Мы свяжемся с вами и сообщим об изменении статуса.",
  },
};

export function OrderOutcome({
  order,
  orderNumber,
  invoiceHref,
}: {
  order: Order | null;
  orderNumber: string;
  invoiceHref?: string;
}) {
  const [paying, setPaying] = useState(false);
  const [payError, setPayError] = useState<string | null>(null);

  const outcome = order ? outcomeOf(order) : "awaiting-payment";
  const view = VIEWS[outcome];
  const Icon = view.icon;

  const pay = async () => {
    if (!order || paying) return;
    setPaying(true);
    setPayError(null);
    try {
      const started = await startOrderPayment(order.order_number, order.access_token);
      if (started.confirmation_url) {
        window.location.assign(started.confirmation_url);
        return;
      }
      // Ссылки нет — значит заказ уже оплачен; покажем это без перезагрузки страницы.
      window.location.reload();
    } catch (err) {
      setPayError(
        err instanceof ApiError
          ? err.message
          : "Не удалось перейти к оплате. Заказ сохранён — попробуйте позже.",
      );
      setPaying(false);
    }
  };

  return (
    <section className="rounded-lg border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <Icon className={`h-14 w-14 shrink-0 ${view.tone}`} strokeWidth={1.5} aria-hidden />
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-3xl font-semibold text-ink">{view.title}</h1>
          <p className="mt-1 text-ink-2">
            Заказ <span className="font-semibold text-accent">№ {order?.order_number ?? orderNumber}</span>
            {order && <> на сумму {formatPrice(Number(order.total), order.currency)}</>}
          </p>
          <p className="mt-1 text-sm text-ink-3">{view.text}</p>

          {outcome === "awaiting-payment" && order && (
            <div className="mt-4">
              <Button variant="accent" onClick={pay} disabled={paying}>
                {paying ? "Переходим к оплате…" : "Оплатить заказ"}
              </Button>
              {payError && (
                <p role="alert" className="mt-2 flex items-start gap-2 text-sm text-danger">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  {payError}
                </p>
              )}
            </div>
          )}

          {outcome === "invoice" && invoiceHref && (
            <div className="mt-4">
              <Link href={invoiceHref}>
                <Button variant="outline">Открыть счёт</Button>
              </Link>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
