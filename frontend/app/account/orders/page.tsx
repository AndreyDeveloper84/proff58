"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronUp, ClipboardList, RotateCcw } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { getMe, getOrders } from "@/lib/auth";
import { formatPrice, pluralize } from "@/lib/format";
import type { Order } from "@/lib/types";
import { cn } from "@/lib/utils";

type OrderTab = "all" | "processing" | "delivered" | "cancelled";

const TABS: { value: OrderTab; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "processing", label: "В обработке" },
  { value: "delivered", label: "Доставленные" },
  { value: "cancelled", label: "Отменённые" },
];

function orderMatchesTab(order: Order, tab: OrderTab) {
  if (tab === "all") return true;
  const status = order.display_status.toLowerCase();
  if (tab === "delivered") {
    return status.includes("достав") || status.includes("выполн");
  }
  if (tab === "cancelled") {
    return status.includes("отмен") || status.includes("возврат");
  }
  return !["достав", "выполн", "отмен", "возврат"].some((token) =>
    status.includes(token),
  );
}

function statusClass(status: string) {
  const value = status.toLowerCase();
  if (value.includes("достав") || value.includes("выполн")) {
    return "bg-accent/10 text-accent";
  }
  if (value.includes("обработ") || value.includes("сбор") || value.includes("подтверж")) {
    return "bg-blue-50 text-blue-700";
  }
  if (value.includes("отмен") || value.includes("возврат")) {
    return "bg-red-50 text-danger";
  }
  return "bg-raised text-ink-2";
}

function orderDate(value: string) {
  return new Date(value).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default function OrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [tab, setTab] = useState<OrderTab>("all");
  const [expandedOrderId, setExpandedOrderId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    getMe().then((user) => {
      if (!user) {
        router.push("/account/login");
        return;
      }
      getOrders().then((data) => {
        if (active) setOrders(data);
      });
    });
    return () => {
      active = false;
    };
  }, [router]);

  const visibleOrders = useMemo(
    () => (orders ?? []).filter((order) => orderMatchesTab(order, tab)),
    [orders, tab],
  );

  return (
    <AccountShell title="Заказы" mobileBackHref="/account/profile">
      <div className="space-y-4">
        <div className="flex gap-2 overflow-x-auto rounded-lg border border-line bg-surface p-2">
          {TABS.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setTab(item.value)}
              className={cn(
                "min-h-9 shrink-0 rounded-md px-3 text-xs font-semibold transition sm:text-sm",
                tab === item.value
                  ? "bg-accent/10 text-accent"
                  : "text-ink-3 hover:bg-raised hover:text-ink",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        {orders === null && (
          <div
            className="h-56 animate-pulse rounded-lg border border-line bg-surface"
            aria-label="Загрузка заказов"
          />
        )}

        {orders !== null && visibleOrders.length === 0 && (
          <section className="rounded-lg border border-line bg-surface px-5 py-12 text-center">
            <ClipboardList className="mx-auto h-10 w-10 text-ink-3" aria-hidden />
            <h2 className="mt-3 text-base font-semibold text-ink">
              {orders.length === 0 ? "Заказов пока нет" : "В этой категории заказов нет"}
            </h2>
            <p className="mx-auto mt-1 max-w-sm text-sm text-ink-3">
              {orders.length === 0
                ? "Оформите первый заказ — здесь появятся его состав, сумма и статус."
                : "Выберите другую вкладку, чтобы посмотреть остальные заказы."}
            </p>
            {orders.length === 0 && (
              <Link
                href="/catalog"
                className="mt-5 inline-flex h-11 items-center rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink"
              >
                Перейти в каталог
              </Link>
            )}
          </section>
        )}

        {visibleOrders.map((order) => (
          <article
            key={order.id}
            id={`order-${order.id}`}
            className="overflow-hidden rounded-lg border border-line bg-surface"
          >
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-4 sm:px-5">
              <div>
                <h2 className="text-sm font-semibold text-ink">№ {order.order_number}</h2>
                <p className="mt-1 text-[11px] text-ink-3">от {orderDate(order.created_at)}</p>
              </div>
              <span
                className={cn(
                  "rounded-md px-2 py-1 text-[11px] font-semibold",
                  statusClass(order.display_status),
                )}
              >
                {order.display_status}
              </span>
            </div>

            <div className="p-4 sm:p-5">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="text-lg font-bold text-ink">
                    {formatPrice(Number(order.total) || 0, order.currency)}
                  </p>
                  <p className="mt-1 text-xs text-ink-3">
                    {order.items.length}{" "}
                    {pluralize(order.items.length, "товар", "товара", "товаров")}
                  </p>
                </div>
                {order.delivery_address && (
                  <p className="max-w-md text-right text-xs leading-5 text-ink-3">
                    {order.delivery_address}
                  </p>
                )}
              </div>

              {order.items.length > 0 && (
                <div className="mt-4 flex gap-3 overflow-x-auto pb-1">
                  {order.items.slice(0, 4).map((item) => (
                    <div
                      key={item.id}
                      className="w-24 shrink-0"
                      title={`${item.name} — ${item.quantity} шт.`}
                    >
                      <div className="grid h-20 place-items-center rounded-md border border-line bg-photo">
                        <Image
                          src="/sample-tool.svg"
                          alt=""
                          width={68}
                          height={68}
                          className="h-16 w-16 object-contain"
                        />
                      </div>
                      <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-ink-2">
                        {item.name}
                      </p>
                    </div>
                  ))}
                  {order.items.length > 4 && (
                    <div className="grid h-20 w-20 shrink-0 place-items-center rounded-md bg-raised text-xs font-semibold text-ink-2">
                      +{order.items.length - 4}
                    </div>
                  )}
                </div>
              )}

              <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
                {(order.display_status.toLowerCase().includes("достав") ||
                  order.display_status.toLowerCase().includes("выполн")) && (
                  <Link
                    href="/catalog"
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line px-4 text-sm font-semibold text-ink transition hover:bg-raised"
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden />
                    Повторить заказ
                  </Link>
                )}
                <button
                  type="button"
                  onClick={() =>
                    setExpandedOrderId((current) => (current === order.id ? null : order.id))
                  }
                  aria-expanded={expandedOrderId === order.id}
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line px-4 text-sm font-semibold text-ink transition hover:bg-raised"
                >
                  {expandedOrderId === order.id ? "Скрыть детали" : "Подробнее"}
                  {expandedOrderId === order.id ? (
                    <ChevronUp className="h-4 w-4" aria-hidden />
                  ) : (
                    <ChevronDown className="h-4 w-4" aria-hidden />
                  )}
                </button>
              </div>

              {expandedOrderId === order.id && (
                <dl className="mt-4 grid gap-3 border-t border-line pt-4 text-sm sm:grid-cols-2">
                  <OrderDetail label="Способ получения" value={order.delivery_method || "Не указан"} />
                  <OrderDetail label="Способ оплаты" value={order.payment_method || "Не указан"} />
                  <OrderDetail
                    label="Адрес доставки"
                    value={order.delivery_address || "Самовывоз"}
                  />
                  <OrderDetail
                    label="Получатель"
                    value={order.customer_name || "Не указан"}
                  />
                </dl>
              )}
            </div>
          </article>
        ))}
      </div>
    </AccountShell>
  );
}

function OrderDetail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-ink">{value}</dd>
    </div>
  );
}
