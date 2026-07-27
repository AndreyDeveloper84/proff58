"use client";

import { useCallback, useRef, useSyncExternalStore } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReservationNotice } from "@/components/order/ReservationNotice";
import { TrackOrderInMaxCta } from "@/components/order/TrackOrderInMaxCta";
import { formatDeliverySlot, formatPrice } from "@/lib/format";
import { readStashedOrder } from "@/lib/order-storage";
import type { Order } from "@/lib/types";

const DELIVERY_LABELS: Record<string, string> = {
  courier: "Курьер",
  pickup: "Самовывоз",
};

const PAYMENT_LABELS: Record<string, string> = {
  online: "Онлайн-оплата",
  invoice: "Счёт для организации",
};

export default function ThanksPage() {
  const params = useParams<{ id: string }>();
  const orderNumber = params.id;

  // Снимок из sessionStorage (сохранён на checkout) — внешнее хранилище: читаем через
  // useSyncExternalStore (корректный SSR: сервер отдаёт null, клиент — реальный снимок).
  // null → graceful fallback (показываем только номер из URL). Подписки нет — данные статичны.
  //
  // Кэш — в useRef (НЕ модульный): useSyncExternalStore сравнивает результат через Object.is,
  // поэтому getSnapshot обязан возвращать стабильную ссылку. Ref делает кэш per-instance —
  // никакого общего состояния между запросами на сервере (ПДн заказа не «протекут» соседу).
  const cacheRef = useRef<{ key: string; value: Order | null } | null>(null);
  const subscribe = useCallback(() => () => {}, []);
  const getSnapshot = useCallback(() => {
    if (!cacheRef.current || cacheRef.current.key !== orderNumber) {
      cacheRef.current = { key: orderNumber, value: readStashedOrder(orderNumber) };
    }
    return cacheRef.current.value;
  }, [orderNumber]);
  const order = useSyncExternalStore(subscribe, getSnapshot, () => null);

  // Сумма товаров из снимка строк: order.total включает доставку, а отдельного
  // поля «товары» бэк не отдаёт.
  const itemsTotal =
    order?.items.reduce((sum, item) => sum + (Number(item.line_total) || 0), 0) ?? 0;

  return (
    <main className="mx-auto w-full max-w-[1400px] px-4 pb-10 pt-5 sm:px-6 lg:px-8 lg:pt-7">
      <ol className="mx-auto mb-5 flex max-w-2xl items-center text-xs font-semibold sm:text-sm">
        {["Корзина", "Оформление", "Заказ принят"].map((label, index) => (
          <li key={label} className="contents">
            {index > 0 && <span className="mx-3 h-px flex-1 bg-accent sm:mx-5" aria-hidden />}
            <span className="flex items-center gap-2 text-accent">
              <span className="grid h-6 w-6 place-items-center rounded-full bg-accent text-accent-ink">
                {index < 2 ? "✓" : "3"}
              </span>
              <span className="whitespace-nowrap">{label}</span>
            </span>
          </li>
        ))}
      </ol>

      <section className="rounded-lg border border-line bg-surface p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <CheckCircle className="h-14 w-14 shrink-0 text-accent" strokeWidth={1.5} aria-hidden />
          <div>
            <h1 className="font-display text-3xl font-semibold text-ink">Спасибо за заказ!</h1>
            <p className="mt-1 text-ink-2">
              Ваш заказ{" "}
              <span className="font-semibold text-accent">
                № {order?.order_number ?? orderNumber}
              </span>{" "}
              принят в обработку
            </p>
            <p className="mt-1 text-sm text-ink-3">
              Мы свяжемся с вами при необходимости и сообщим об изменении статуса.
            </p>
          </div>
        </div>
        {order && <div className="mt-5"><ReservationNotice order={order} /></div>}
        {!order && (
          <div className="mt-5 rounded-md border border-line bg-raised px-4 py-3 text-sm text-ink-2">
            Детали заказа не сохранились в этом браузере — на заказ это не влияет. Статус доступен{" "}
            <Link href="/account/orders" className="font-semibold text-accent hover:underline">
              в личном кабинете
            </Link>.
          </div>
        )}
      </section>

      {order && (
        <div className="mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-5">
            <section className="rounded-lg border border-line bg-surface p-5">
              <h2 className="mb-3 text-lg font-semibold text-ink">Состав заказа</h2>
              <div className="divide-y divide-line">
                {order.items.map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-4 py-3 text-sm">
                    <span className="min-w-0 flex-1 text-ink-2">
                      {item.name}
                      <span className="ml-2 text-ink-3">× {item.quantity}</span>
                    </span>
                    <span className="shrink-0 font-semibold text-ink">
                      {item.line_total ? formatPrice(Number(item.line_total), order.currency) : "—"}
                    </span>
                  </div>
                ))}
              </div>
              <div className="ml-auto mt-4 max-w-sm space-y-2 border-t border-line pt-4 text-sm">
                <div className="flex justify-between gap-3">
                  <span className="text-ink-3">Товары</span>
                  <span>{formatPrice(itemsTotal, order.currency)}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-ink-3">Доставка</span>
                  <span>
                    {order.delivery_cost === null
                      ? "уточнит менеджер"
                      : Number(order.delivery_cost) === 0
                        ? "бесплатно"
                        : formatPrice(Number(order.delivery_cost), order.currency)}
                  </span>
                </div>
                {order.vat_rate > 0 && (
                  <div className="flex justify-between gap-3">
                    <span className="text-ink-3">В т.ч. НДС {order.vat_rate}%</span>
                    <span>{formatPrice(Number(order.vat_amount) || 0, order.currency)}</span>
                  </div>
                )}
                <div className="flex justify-between gap-3 border-t border-line pt-3 text-lg font-bold">
                  <span>{order.delivery_cost === null ? "Предварительный итог:" : "Итого:"}</span>
                  <span>{formatPrice(Number(order.total), order.currency)}</span>
                </div>
              </div>
            </section>

            <section className="rounded-lg border border-line bg-surface p-5">
              <h2 className="text-lg font-semibold text-ink">Доставка</h2>
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-ink-3">Способ получения</dt><dd className="mt-1 text-ink">{DELIVERY_LABELS[order.delivery_method] ?? order.delivery_method}</dd></div>
                {order.delivery_slot && <div><dt className="text-ink-3">Дата и время</dt><dd className="mt-1 text-ink">{formatDeliverySlot(order.delivery_slot)}</dd></div>}
                {order.delivery_address && <div className="sm:col-span-2"><dt className="text-ink-3">Адрес</dt><dd className="mt-1 text-ink">{order.delivery_address}</dd></div>}
              </dl>
            </section>
          </div>

          <aside className="space-y-5 lg:sticky lg:top-24">
            <section className="rounded-lg border border-line bg-surface p-5">
              <h2 className="text-lg font-semibold text-ink">Детали заказа</h2>
              <dl className="mt-3 divide-y divide-line text-sm">
                <div className="flex justify-between gap-3 py-2"><dt className="text-ink-3">Номер</dt><dd className="font-semibold text-ink">{order.order_number}</dd></div>
                <div className="flex justify-between gap-3 py-2"><dt className="text-ink-3">Статус</dt><dd className="text-right text-ink">{order.display_status}</dd></div>
                <div className="flex justify-between gap-3 py-2"><dt className="text-ink-3">Оплата</dt><dd className="text-right text-ink">{PAYMENT_LABELS[order.payment_method] ?? order.payment_method}</dd></div>
                <div className="flex justify-between gap-3 py-2"><dt className="text-ink-3">Получатель</dt><dd className="text-right text-ink">{order.customer_name}</dd></div>
                <div className="flex justify-between gap-3 py-2"><dt className="text-ink-3">Телефон</dt><dd className="text-right text-ink">{order.customer_phone}</dd></div>
              </dl>
            </section>
            {order.access_token && (
              <TrackOrderInMaxCta orderNumber={order.order_number} accessToken={order.access_token} />
            )}
          </aside>
        </div>
      )}

      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Link href="/account/orders"><Button variant="outline">Перейти в личный кабинет</Button></Link>
        <Link href="/catalog"><Button variant="accent">Вернуться в каталог</Button></Link>
      </div>
    </main>
  );
}
