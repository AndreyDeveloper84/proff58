"use client";

import { useCallback, useRef, useSyncExternalStore } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/format";
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
                    {item.line_total ? formatPrice(Number(item.line_total)) : "—"}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
              <span className="text-lg text-ink-2">Итого:</span>
              <span className="font-display text-2xl font-bold text-ink">
                {formatPrice(Number(order.total))}
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
