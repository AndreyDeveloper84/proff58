"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Building2,
  ChevronLeft,
  CreditCard,
  ExternalLink,
  FileText,
  MapPin,
  Package,
  Phone,
  ReceiptText,
  ShoppingBag,
  Truck,
  UserRound,
} from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { AccountDialog } from "@/components/account/AccountDialog";
import { ReservationNotice } from "@/components/order/ReservationNotice";
import { ReviewForm } from "@/components/reviews/ReviewForm";
import { StarDisplay } from "@/components/reviews/StarRating";
import { getMe, getOrder } from "@/lib/auth";
import { formatDeliverySlot, formatPrice, humanizeToken, pluralize } from "@/lib/format";
import { isDelivered, statusBadgeClass } from "@/lib/order-status";
import { getMyReviewForOrder } from "@/lib/reviews";
import type { MyReview } from "@/lib/types";
import type { Order, OrderItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAYMENT_STATUS_LABELS: Record<Order["payment_status"], string> = {
  pending: "Ожидает оплаты",
  paid: "Оплачен",
  expired: "Срок оплаты истёк",
  partially_refunded: "Частичный возврат",
  refunded: "Возвращён",
};

const PAYMENT_METHOD_LABELS: Record<string, string> = {
  card: "Банковская карта",
  cash: "Наличными",
  online: "Онлайн-оплата",
  invoice: "Оплата по счёту",
  yookassa: "Онлайн-оплата",
};

const DELIVERY_METHOD_LABELS: Record<string, string> = {
  courier: "Курьерская доставка",
  delivery: "Доставка",
  pickup: "Самовывоз",
  transport_company: "Транспортная компания",
};

function dateTime(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function displayToken(value: string, labels: Record<string, string>) {
  if (!value) return "Не указан";
  return labels[value] ?? humanizeToken(value);
}

function itemPrice(item: OrderItem) {
  return Number(item.price_final ?? item.price_base ?? 0);
}

function OrderLoading() {
  return (
    <AccountShell title="Детали заказа" mobileBackHref="/account/orders">
      <div className="space-y-4" aria-label="Загрузка заказа">
        <div className="h-40 animate-pulse rounded-lg border border-line bg-surface" />
        <div className="grid gap-4 md:grid-cols-2">
          <div className="h-48 animate-pulse rounded-lg border border-line bg-surface" />
          <div className="h-48 animate-pulse rounded-lg border border-line bg-surface" />
        </div>
        <div className="h-72 animate-pulse rounded-lg border border-line bg-surface" />
      </div>
    </AccountShell>
  );
}

export default function OrderDetailsPage() {
  const router = useRouter();
  const params = useParams<{ number: string }>();
  const orderNumber = params.number;
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // #573: null — отзыва нет (показать CTA), "disabled" — фича выключена, undefined — не грузили.
  const [review, setReview] = useState<MyReview | null | "disabled" | undefined>(undefined);
  const [reviewOpen, setReviewOpen] = useState(false);

  useEffect(() => {
    let active = true;
    getMe()
      .then((user) => {
        if (!user) {
          router.push("/account/login");
          return null;
        }
        return getOrder(orderNumber);
      })
      .then((data) => {
        if (!active || !data) return;
        setOrder(data);
        if (isDelivered(data)) {
          getMyReviewForOrder(data.order_number).then((r) => {
            if (active) setReview(r);
          });
        }
      })
      .catch((caught) => {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : "Не удалось загрузить заказ.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [orderNumber, router]);

  const itemsTotal = useMemo(
    () =>
      order?.items.reduce(
        (sum, item) => sum + (Number(item.line_total) || itemPrice(item) * item.quantity),
        0,
      ) ?? 0,
    [order],
  );

  if (loading) return <OrderLoading />;

  if (!order) {
    return (
      <AccountShell title="Детали заказа" mobileBackHref="/account/orders">
        <section className="rounded-lg border border-line bg-surface px-5 py-12 text-center">
          <ReceiptText className="mx-auto h-10 w-10 text-ink-3" aria-hidden />
          <h2 className="mt-3 text-base font-semibold text-ink">Заказ не найден</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-ink-3">
            {error || "Возможно, заказ был удалён или принадлежит другому аккаунту."}
          </p>
          <Link
            href="/account/orders"
            className="mt-5 inline-flex h-11 items-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
            Вернуться к заказам
          </Link>
        </section>
      </AccountShell>
    );
  }

  const isB2B = order.customer_type === "b2b";
  const deliveryCost =
    order.delivery_cost === null ? null : Number(order.delivery_cost) || 0;

  return (
    <AccountShell
      title={`Заказ № ${order.order_number}`}
      mobileBackHref="/account/orders"
    >
      <div className="space-y-5">
        <section className="overflow-hidden rounded-lg border border-line bg-surface">
          <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between lg:p-6">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-semibold",
                    statusBadgeClass(order),
                  )}
                >
                  {order.display_status}
                </span>
                <span className="rounded-md bg-raised px-2.5 py-1 text-xs font-medium text-ink-2">
                  {PAYMENT_STATUS_LABELS[order.payment_status]}
                </span>
              </div>
              <p className="mt-3 text-sm text-ink-3">Оформлен {dateTime(order.created_at)}</p>
              <p className="mt-1 text-xs text-ink-3">
                {order.items.length}{" "}
                {pluralize(order.items.length, "товар", "товара", "товаров")}
              </p>
            </div>
            <div className="sm:text-right">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-3">
                {deliveryCost === null ? "Предварительный итог" : "Итого"}
              </p>
              <p className="mt-1 text-2xl font-bold text-ink">
                {formatPrice(Number(order.total) || 0, order.currency)}
              </p>
            </div>
          </div>
          {isB2B && (
            <div className="flex flex-col gap-3 border-t border-line bg-raised/50 px-5 py-4 sm:flex-row sm:items-center sm:justify-between lg:px-6">
              <div className="flex items-start gap-3">
                <FileText className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
                <div>
                  <p className="text-sm font-semibold text-ink">Счёт на оплату</p>
                  <p className="mt-0.5 text-xs text-ink-3">
                    Откроется в новой вкладке — документ можно сохранить или распечатать.
                  </p>
                </div>
              </div>
              <a
                href={`/api/orders/${encodeURIComponent(order.order_number)}/invoice`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink transition hover:brightness-110"
              >
                Открыть счёт
                <ExternalLink className="h-4 w-4" aria-hidden />
              </a>
            </div>
          )}
        </section>

        <div className="grid gap-5 md:grid-cols-2">
          <InfoCard icon={Truck} title="Доставка">
            <InfoRow
              label="Способ получения"
              value={displayToken(order.delivery_method, DELIVERY_METHOD_LABELS)}
            />
            <InfoRow
              label="Адрес"
              value={order.delivery_address || "Пункт самовывоза"}
              icon={MapPin}
            />
            {order.delivery_zone && (
              <InfoRow label="Зона доставки" value={humanizeToken(order.delivery_zone)} />
            )}
            {order.delivery_slot && (
              <InfoRow
                label="Дата и время доставки"
                value={formatDeliverySlot(order.delivery_slot)}
              />
            )}
          </InfoCard>

          <InfoCard icon={CreditCard} title="Оплата">
            <InfoRow
              label="Способ оплаты"
              value={displayToken(order.payment_method, PAYMENT_METHOD_LABELS)}
            />
            <InfoRow label="Статус" value={PAYMENT_STATUS_LABELS[order.payment_status]} />
            <div>
              <ReservationNotice order={order} />
            </div>
          </InfoCard>

          <InfoCard icon={UserRound} title="Получатель">
            <InfoRow label="Имя" value={order.customer_name || "Не указано"} />
            <InfoRow label="Телефон" value={order.customer_phone || "Не указан"} icon={Phone} />
            <InfoRow label="Email" value={order.customer_email || "Не указан"} />
          </InfoCard>

          {isB2B && (
            <InfoCard icon={Building2} title="Реквизиты покупателя">
              <InfoRow label="Организация" value={order.company_name || "Не указана"} />
              <div className="grid grid-cols-2 gap-3">
                <InfoRow label="ИНН" value={order.inn || "Не указан"} />
                <InfoRow label="КПП" value={order.kpp || "Не указан"} />
              </div>
              <InfoRow label="Юридический адрес" value={order.legal_address || "Не указан"} />
            </InfoCard>
          )}
        </div>

        <section className="overflow-hidden rounded-lg border border-line bg-surface">
          <div className="flex items-center gap-2 border-b border-line px-4 py-4 sm:px-5">
            <ShoppingBag className="h-5 w-5 text-accent" aria-hidden />
            <h2 className="text-sm font-semibold text-ink">Состав заказа</h2>
            <span className="ml-auto rounded-full bg-raised px-2.5 py-1 text-xs font-semibold text-ink-2">
              {order.items.length}
            </span>
          </div>

          <div className="hidden grid-cols-[minmax(0,1fr)_110px_90px_130px] gap-4 border-b border-line bg-raised/60 px-5 py-2.5 text-xs font-medium text-ink-3 md:grid">
            <span>Товар</span>
            <span className="text-right">Цена</span>
            <span className="text-center">Количество</span>
            <span className="text-right">Сумма</span>
          </div>

          <div>
            {order.items.map((item) => (
              <OrderLine key={item.id} item={item} orderCurrency={order.currency} />
            ))}
          </div>

          <div className="border-t border-line bg-raised/30 px-4 py-5 sm:px-5">
            <dl className="ml-auto max-w-sm space-y-3">
              <TotalRow
                label="Стоимость товаров"
                value={formatPrice(itemsTotal, order.currency)}
              />
              <TotalRow
                label="Доставка"
                value={
                  deliveryCost === null
                    ? "Уточняется менеджером"
                    : deliveryCost === 0
                      ? "Бесплатно"
                      : formatPrice(deliveryCost, order.currency)
                }
              />
              {isB2B && (
                <div className="space-y-2 rounded-md bg-raised px-3 py-2.5">
                  <TotalRow
                    label="Сумма без НДС"
                    value={formatPrice(Number(order.amount_without_vat) || 0, order.currency)}
                  />
                  <TotalRow
                    label={`В том числе НДС ${order.vat_rate}%`}
                    value={formatPrice(Number(order.vat_amount) || 0, order.currency)}
                  />
                </div>
              )}
              <div className="border-t border-line pt-3">
                <TotalRow
                  label={deliveryCost === null ? "Предварительный итог" : "Итого"}
                  value={formatPrice(Number(order.total) || 0, order.currency)}
                  total
                />
              </div>
            </dl>
          </div>
        </section>

        {isDelivered(order) && review !== "disabled" && review !== undefined && (
          <section className="rounded-lg border border-line bg-surface p-5">
            <h2 className="text-sm font-semibold text-ink">Отзыв о заказе</h2>
            {review === null ? (
              <div className="mt-3">
                <p className="text-sm text-ink-2">
                  Заказ получен — поделитесь впечатлением о товарах, доставке и магазине.
                </p>
                <button
                  type="button"
                  onClick={() => setReviewOpen(true)}
                  className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink"
                >
                  Оставить отзыв
                </button>
              </div>
            ) : (
              <div className="mt-3 space-y-2 text-sm">
                <StarDisplay value={review.product_rating} />
                {review.status === "pending" && (
                  <p className="text-ink-2">Спасибо! Отзыв отправлен на модерацию.</p>
                )}
                {review.status === "approved" && (
                  <p className="text-accent">Отзыв опубликован.</p>
                )}
                {review.status === "rejected" && (
                  <p className="text-danger">
                    Отзыв отклонён{review.rejection_reason ? `: ${review.rejection_reason}` : "."}
                  </p>
                )}
              </div>
            )}
          </section>
        )}

        <AccountDialog
          title="Отзыв о заказе"
          description="Оценки обязательны, текст — по желанию. Отзыв появится после модерации."
          open={reviewOpen}
          onClose={() => setReviewOpen(false)}
        >
          <ReviewForm
            orderNumber={order.order_number}
            onCancel={() => setReviewOpen(false)}
            onDone={(created) => {
              setReview(created);
              setReviewOpen(false);
            }}
          />
        </AccountDialog>

        {order.comment && (
          <section className="rounded-lg border border-line bg-surface p-5">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Package className="h-4 w-4 text-accent" aria-hidden />
              Комментарий к заказу
            </h2>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-ink-2">
              {order.comment}
            </p>
          </section>
        )}
      </div>
    </AccountShell>
  );
}

function InfoCard({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Truck;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Icon className="h-5 w-5 text-accent" aria-hidden />
        {title}
      </h2>
      <dl className="mt-4 space-y-3">{children}</dl>
    </section>
  );
}

function InfoRow({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon?: typeof MapPin;
}) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-1 flex items-start gap-1.5 break-words text-sm font-medium text-ink">
        {Icon && <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-3" aria-hidden />}
        {value}
      </dd>
    </div>
  );
}

function OrderLine({ item, orderCurrency }: { item: OrderItem; orderCurrency: string }) {
  const currency = item.currency || orderCurrency;
  const lineTotal = Number(item.line_total) || itemPrice(item) * item.quantity;
  return (
    <div className="grid gap-3 border-b border-line px-4 py-4 last:border-b-0 md:grid-cols-[minmax(0,1fr)_110px_90px_130px] md:items-center md:gap-4 md:px-5">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid h-16 w-16 shrink-0 place-items-center rounded-md bg-photo">
          <Image
            src="/sample-tool.svg"
            alt=""
            width={56}
            height={56}
            className="h-12 w-12 object-contain"
          />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-5 text-ink">{item.name}</p>
          <p className="mt-1 text-xs text-ink-3">
            {item.article ? `Арт. ${item.article}` : item.code_1c ? `Код ${item.code_1c}` : ""}
          </p>
        </div>
      </div>
      <div className="flex justify-between text-sm md:block md:text-right">
        <span className="text-xs text-ink-3 md:hidden">Цена</span>
        <span className="font-medium text-ink">{formatPrice(itemPrice(item), currency)}</span>
      </div>
      <div className="flex justify-between text-sm md:block md:text-center">
        <span className="text-xs text-ink-3 md:hidden">Количество</span>
        <span className="font-medium text-ink">
          {item.quantity} {item.unit || "шт."}
        </span>
      </div>
      <div className="flex justify-between text-sm md:block md:text-right">
        <span className="text-xs text-ink-3 md:hidden">Сумма</span>
        <span className="font-semibold text-ink">{formatPrice(lineTotal, currency)}</span>
      </div>
    </div>
  );
}

function TotalRow({
  label,
  value,
  total = false,
}: {
  label: string;
  value: string;
  total?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className={total ? "text-base font-semibold text-ink" : "text-sm text-ink-3"}>
        {label}
      </dt>
      <dd className={total ? "text-lg font-bold text-ink" : "text-sm font-semibold text-ink"}>
        {value}
      </dd>
    </div>
  );
}
