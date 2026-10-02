"use client";

import Link from "next/link";
import { CheckCircle, Clock, FileText, RotateCcw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PayOrderButton } from "@/components/order/PayOrderButton";
import { isPaidOnPickup } from "@/lib/payment-methods";
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
 * Состояния читаются по полям заказа: способу оплаты, статусу платежа и оси
 * обработки. Ничего не додумываем — если сервер говорит «ожидает», так и пишем.
 *
 * Отмена проверяется первой (DRF-2736). Страница оплаты у кассы живёт дольше,
 * чем резерв товара: заказ мог быть отменён, пока покупатель вводил данные карты.
 * Раньше он возвращался сюда и видел «ожидает оплаты» с кнопкой «Оплатить» —
 * по заказу, которого уже нет, — а если успевал оплатить, то не видел ничего о
 * своих деньгах.
 */
type Outcome =
  | "paid"
  | "awaiting-payment"
  | "delivery-pending"
  | "invoice"
  | "on-delivery"
  | "cancelled"
  | "cancelled-unpaid"
  | "cancelled-paid"
  | "cancelled-paid-offline"
  | "cancelled-refunded";

function outcomeOf(order: Order): Outcome {
  if (order.fulfillment_status === "cancelled") {
    if (order.payment_status === "paid" || order.payment_status === "partially_refunded") {
      return order.payment_method === "online" ? "cancelled-paid" : "cancelled-paid-offline";
    }
    if (order.payment_status === "refunded") return "cancelled-refunded";
    if (order.payment_status === "expired") return "cancelled-unpaid";
    return "cancelled";
  }
  if (order.payment_method === "invoice") return "invoice";
  // Наличные и карта на выдаче — оба про оплату в магазине. Проверять их по
  // одному коду значило бы звать в кассу того, кто собрался платить картой на месте.
  if (isPaidOnPickup(order.payment_method)) return "on-delivery";
  if (order.payment_status === "paid") return "paid";
  // DRF-2299: стоимость доставки ещё не рассчитана — итог предварительный,
  // сервер оплату не откроет; звать «Оплатить» было бы обманом.
  if (order.delivery_calc_status === "manual_required") return "delivery-pending";
  return "awaiting-payment";
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
  "delivery-pending": {
    icon: Clock,
    tone: "text-hit",
    title: "Заказ принят, стоимость доставки уточняется",
    text: "Сумма пока без доставки. Менеджер рассчитает её и свяжется с вами — после этого станет доступна оплата.",
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
  cancelled: {
    icon: XCircle,
    tone: "text-ink-3",
    title: "Заказ отменён",
    text: "Оплачивать его не нужно. Если товар всё ещё нужен — оформите новый заказ.",
  },
  "cancelled-unpaid": {
    icon: XCircle,
    tone: "text-ink-3",
    title: "Заказ отменён",
    text: "Оплата не поступила в срок, и товар вернулся в продажу. Оплачивать этот заказ не нужно — если товар всё ещё нужен, оформите новый.",
  },
  // Оплата пришла после отмены либо заказ отменили уже оплаченным — покупателю
  // важно одно: деньги вернут, и делать для этого ничего не нужно.
  "cancelled-paid": {
    icon: RotateCcw,
    tone: "text-hit",
    title: "Заказ отменён, оплата получена",
    text: "Оплата по заказу получена, деньги мы вернём. Заявка на возврат создана автоматически — подавать её не нужно.",
  },
  // Оплата не через кассу (счёт организации): автоматической заявки нет.
  "cancelled-paid-offline": {
    icon: RotateCcw,
    tone: "text-hit",
    title: "Заказ отменён, оплата получена",
    text: "Оплата по заказу получена. Мы свяжемся с вами, чтобы вернуть деньги.",
  },
  "cancelled-refunded": {
    icon: XCircle,
    tone: "text-ink-3",
    title: "Заказ отменён, деньги возвращены",
    text: "Возврат оформлен. Срок зачисления зависит от банка, выпустившего карту.",
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
  const outcome = order ? outcomeOf(order) : "awaiting-payment";
  const view = VIEWS[outcome];
  const Icon = view.icon;
  return (
    <section className="rounded-lg border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <Icon className={`h-14 w-14 shrink-0 ${view.tone}`} strokeWidth={1.5} aria-hidden />
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-3xl font-semibold text-ink">{view.title}</h1>
          <p className="mt-1 text-ink-2">
            Заказ <span className="font-semibold text-accent">№ {order?.order_number ?? orderNumber}</span>
            {order && (
              <>
                {" "}
                на сумму {formatPrice(Number(order.total), order.currency)}
                {outcome === "delivery-pending" && " (без доставки)"}
              </>
            )}
          </p>
          <p className="mt-1 text-sm text-ink-3">{view.text}</p>

          {outcome === "awaiting-payment" && order && (
            <PayOrderButton
              orderNumber={order.order_number}
              accessToken={order.access_token}
              className="mt-4"
            />
          )}

          {(outcome === "cancelled-paid" || outcome === "cancelled-paid-offline") && (
            <p className="mt-2 text-sm text-ink-2">
              Хотите получить товар или остались вопросы — свяжитесь с нами:{" "}
              <Link href="/info/about" className="font-semibold text-accent hover:underline">
                контакты
              </Link>
              .
            </p>
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
