"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, ClipboardList, Clock3, RotateCcw, Star } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { reservationState } from "@/components/order/ReservationNotice";
import { checkAuth, getOrders, loginHref } from "@/lib/auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { formatDate, formatDateTime, formatPrice, pluralize } from "@/lib/format";
import { isCancelled, isDelivered, isInProgress, statusBadgeClass } from "@/lib/order-status";
import type { Order } from "@/lib/types";
import { cn } from "@/lib/utils";

type OrderTab = "all" | "processing" | "delivered" | "cancelled";

const TABS: { value: OrderTab; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "processing", label: "В обработке" },
  { value: "delivered", label: "Доставленные" },
  { value: "cancelled", label: "Отменённые" },
];

// Вкладки — по машиночитаемым осям (lib/order-status), не по разбору display_status:
// «В доставке» (shipped) — это ещё «В обработке», а не «Доставленные».
function orderMatchesTab(order: Order, tab: OrderTab) {
  if (tab === "all") return true;
  if (tab === "delivered") return isDelivered(order);
  if (tab === "cancelled") return isCancelled(order);
  return isInProgress(order);
}

export default function OrdersPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [orders, setOrders] = useState<Order[] | null>(null);
  // #574: сбой загрузки — своё состояние, иначе экран показывал «Заказов пока нет».
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<OrderTab>("all");

  useEffect(() => {
    let active = true;
    checkAuth().then((user) => {
      if (!active) return;
      // replace, а не push: иначе «Назад» с формы входа возвращает сюда, страница
      // снова выкидывает на вход — и человек застревает в петле.
      if (user === "anonymous") {
        router.replace(loginHref(pathname));
        return;
      }
      if (user === "error") {
        setFailed(true);
        return;
      }
      getOrders().then((data) => {
        if (!active) return;
        if (data === "error") setFailed(true);
        else setOrders(data);
      });
    });
    return () => {
      active = false;
    };
  }, [router, pathname]);

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

        {failed && (
          <ErrorState
            title="Не удалось загрузить заказы"
            description="Проверьте соединение и обновите страницу — заказы никуда не пропали."
          />
        )}

        {!failed && orders === null && <LoadingState label="Загружаем заказы…" />}

        {!failed && orders !== null && visibleOrders.length === 0 && (
          <EmptyState
            icon={<ClipboardList className="h-10 w-10" aria-hidden />}
            title={orders.length === 0 ? "Заказов пока нет" : "В этой категории заказов нет"}
            description={
              orders.length === 0
                ? "Оформите первый заказ — здесь появятся его состав, сумма и статус."
                : "Выберите другую вкладку, чтобы посмотреть остальные заказы."
            }
            action={
              orders.length === 0 ? (
                <Link
                  href="/catalog"
                  className="inline-flex h-11 items-center rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink"
                >
                  Перейти в каталог
                </Link>
              ) : undefined
            }
          />
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
                <p className="mt-1 text-[11px] text-ink-3">от {formatDate(order.created_at)}</p>
              </div>
              <span
                className={cn(
                  "rounded-md px-2 py-1 text-[11px] font-semibold",
                  statusBadgeClass(order),
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
                  <p className="max-w-md text-xs leading-5 text-ink-3 sm:text-right">
                    {order.delivery_address}
                  </p>
                )}
              </div>

              {/* #574: резерв виден и в списке. Раньше «ждём оплату» показывалось,
                  а то, что резерв тикает или уже истёк, — только внутри заказа. */}
              {reservationState(order) === "held" && (
                <p className="mt-3 flex items-center gap-1.5 rounded-md border border-info-line bg-info-bg px-3 py-2 text-xs text-info">
                  <Clock3 className="h-4 w-4 shrink-0" aria-hidden />
                  Товар зарезервирован до {formatDateTime(order.reserved_until!)}
                </p>
              )}
              {reservationState(order) === "expired" && (
                <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  Время резерва истекло — наличие подтвердит менеджер.
                </p>
              )}

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
                {/* «Повторить заказ» — только для реально завершённых. Раньше матчился
                    токен "достав", и кнопка светилась у заказа «В доставке» (ещё едет). */}
                {isDelivered(order) && (
                  <Link
                    href="/catalog"
                    className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-line px-4 text-sm font-semibold text-ink transition hover:bg-raised sm:h-10"
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden />
                    Повторить заказ
                  </Link>
                )}
                {/* #574: «Оставить отзыв» была только внутри заказа — из списка
                    доставленных заказов путь к отзыву не просматривался.
                    Форма живёт на странице заказа, поэтому ведём туда якорем.
                    #573 B2B: юрлицам отзывы в Wave 1 недоступны — путь скрыт. */}
                {isDelivered(order) && order.customer_type !== "b2b" && (
                  <Link
                    href={`/account/orders/${encodeURIComponent(order.order_number)}#review`}
                    className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-line px-4 text-sm font-semibold text-ink transition hover:bg-raised sm:h-10"
                  >
                    <Star className="h-4 w-4" aria-hidden />
                    Оставить отзыв
                  </Link>
                )}
                <Link
                  href={`/account/orders/${encodeURIComponent(order.order_number)}`}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink transition hover:brightness-110 sm:h-10"
                >
                  Открыть заказ
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </Link>
              </div>
            </div>
          </article>
        ))}
      </div>
    </AccountShell>
  );
}
