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
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="flex flex-col items-center gap-4 text-center">
        <CheckCircle className="h-16 w-16 text-brand" strokeWidth={1.5} aria-hidden />
        <h1 className="font-display text-3xl font-semibold uppercase tracking-wide text-ink">
          Спасибо за заказ!
        </h1>
        <p className="text-ink-2">
          Ваш заказ{" "}
          <span className="font-display font-semibold text-accent">
            {order?.order_number ?? orderNumber}
          </span>{" "}
          принят в обработку
        </p>
        <p className="max-w-md text-sm text-ink-3">
          Мы свяжемся с вами для подтверждения. Если есть вопросы — позвоните нам или
          напишите на почту.
        </p>
        {/* #574: резерв — сразу под подтверждением, а не внизу карточки деталей:
            срок короткий, и увидеть его нужно первым делом. */}
        {order && <ReservationNotice order={order} />}
        {order?.access_token && (
          <TrackOrderInMaxCta orderNumber={order.order_number} accessToken={order.access_token} />
        )}
        {/* #574: без снимка заказа страница показывала голый номер и ничего больше.
            Объясняем, что заказ создан, и даём путь к нему. */}
        {!order && (
          <div className="rounded-lg border border-line bg-surface px-4 py-3 text-sm text-ink-2">
            Детали заказа не сохранились в этом браузере — на сам заказ это не влияет.
            Состав и статус смотрите{" "}
            <Link href="/account/orders" className="font-semibold text-accent hover:underline">
              в личном кабинете
            </Link>
            .
          </div>
        )}
      </div>

      {order && (
        <div className="mt-8 space-y-4">
          <div className="rounded-lg border border-line bg-surface p-5">
            <h2 className="mb-3 font-display text-lg font-semibold uppercase text-ink">
              Детали заказа
            </h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-ink-3">Статус</span>
                <span className="text-ink">{order.display_status}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink-3">Доставка</span>
                <span className="text-ink">
                  {DELIVERY_LABELS[order.delivery_method] ?? (order.delivery_method || "—")}
                </span>
              </div>
              {order.delivery_slot && (
                <div className="flex justify-between">
                  <span className="text-ink-3">Дата и время доставки</span>
                  <span className="text-ink">{formatDeliverySlot(order.delivery_slot)}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-ink-3">Оплата</span>
                <span className="text-ink">
                  {PAYMENT_LABELS[order.payment_method] ?? (order.payment_method || "—")}
                </span>
              </div>
              {order.delivery_address && (
                <div className="flex justify-between gap-4">
                  <span className="text-ink-3">Адрес</span>
                  <span className="text-right text-ink">{order.delivery_address}</span>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-line bg-surface p-5">
            <h2 className="mb-3 font-display text-lg font-semibold uppercase text-ink">
              Состав заказа
            </h2>
            <div className="space-y-2">
              {order.items.map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate text-ink-2">
                    {item.name}
                    <span className="text-ink-3"> × {item.quantity}</span>
                  </span>
                  <span className="shrink-0 font-display font-semibold text-ink">
                    {item.line_total ? formatPrice(Number(item.line_total), order.currency) : "—"}
                  </span>
                </div>
              ))}
            </div>
            {/* #574: итог был одной строкой без разбивки — покупатель не понимал,
                вошла ли доставка в сумму. Раскладываем по снимку заказа; валюта
                берётся из заказа, как в кабинете. */}
            <div className="mt-3 space-y-1 border-t border-line pt-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 flex-1 truncate text-ink-2">Товары</span>
                <span className="shrink-0 text-ink">{formatPrice(itemsTotal, order.currency)}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 flex-1 truncate text-ink-2">Доставка</span>
                <span className="shrink-0 text-ink">
                  {order.delivery_cost === null
                    ? "уточнит менеджер"
                    : Number(order.delivery_cost) === 0
                      ? "бесплатно"
                      : formatPrice(Number(order.delivery_cost), order.currency)}
                </span>
              </div>
              {order.vat_rate > 0 && (
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 flex-1 truncate text-ink-2">
                    В т.ч. НДС {order.vat_rate}%
                  </span>
                  <span className="shrink-0 text-ink">
                    {formatPrice(Number(order.vat_amount) || 0, order.currency)}
                  </span>
                </div>
              )}
            </div>
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3">
              <span className="min-w-0 flex-1 text-lg text-ink-2">
                {order.delivery_cost === null ? "Предварительный итог:" : "Итого:"}
              </span>
              <span className="shrink-0 font-display text-2xl font-bold text-ink">
                {formatPrice(Number(order.total), order.currency)}
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="mt-8 flex justify-center gap-4">
        <Link href="/">
          <Button variant="outline">На главную</Button>
        </Link>
        <Link href="/catalog">
          <Button variant="accent">Продолжить покупки</Button>
        </Link>
      </div>
    </main>
  );
}
