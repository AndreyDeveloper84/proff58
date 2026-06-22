"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/format";
import type { Order } from "@/lib/orders";

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
  const orderId = params.id;

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Данные заказа из sessionStorage (сохранены при POST /api/orders/ на checkout).
    // GET /api/orders/{number}/ требует аутентификации — для гостей недоступен.
    try {
      const stored = sessionStorage.getItem(`order_${orderId}`);
      if (stored) {
        setOrder(JSON.parse(stored) as Order);
      }
    } catch {
      // sessionStorage недоступен
    }
    setLoading(false);
  }, [orderId]);

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="flex flex-col items-center gap-4 text-center">
        <CheckCircle className="h-16 w-16 text-brand" strokeWidth={1.5} />
        <h1 className="font-display text-3xl font-semibold uppercase tracking-wide text-ink">
          Спасибо за заказ!
        </h1>
        <p className="text-ink-2">
          Ваш заказ{" "}
          <span className="font-display font-semibold text-accent">
            {order?.order_number ?? orderId}
          </span>{" "}
          принят в обработку
        </p>
        <p className="max-w-md text-sm text-ink-3">
          Мы свяжемся с вами для подтверждения заказа. Если у вас есть вопросы,
          позвоните нам или напишите на почту.
        </p>
      </div>

      {order && (
        <div className="mt-8 space-y-4">
          {/* Информация о заказе */}
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
                  {DELIVERY_LABELS[order.delivery_method] ??
                    order.delivery_method}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-ink-3">Оплата</span>
                <span className="text-ink">
                  {PAYMENT_LABELS[order.payment_method] ??
                    order.payment_method}
                </span>
              </div>
              {order.delivery_address && (
                <div className="flex justify-between">
                  <span className="text-ink-3">Адрес</span>
                  <span className="text-right text-ink">
                    {order.delivery_address}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Состав заказа */}
          <div className="rounded-lg border border-line bg-surface p-5">
            <h2 className="mb-3 font-display text-lg font-semibold uppercase text-ink">
              Состав заказа
            </h2>
            <div className="space-y-2">
              {order.items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between gap-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate text-ink-2">
                    {item.name}
                    <span className="text-ink-3"> x {item.quantity}</span>
                  </span>
                  <span className="shrink-0 font-display font-semibold text-ink">
                    {item.line_total
                      ? formatPrice(Number(item.line_total))
                      : "—"}
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
        <a href="/">
          <Button variant="outline">На главную</Button>
        </a>
        <a href="/catalog/perforatory">
          <Button variant="accent">Продолжить покупки</Button>
        </a>
      </div>
    </main>
  );
}
