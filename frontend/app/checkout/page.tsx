"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/format";
import type { Cart } from "@/lib/cart";
import { getCart } from "@/lib/cart";
import { placeOrder } from "@/lib/orders";

type DeliveryMethod = "courier" | "pickup";
type PaymentMethod = "online" | "invoice";

export default function CheckoutPage() {
  const router = useRouter();
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Поля формы
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [comment, setComment] = useState("");
  const [delivery, setDelivery] = useState<DeliveryMethod>("courier");
  const [payment, setPayment] = useState<PaymentMethod>("online");

  useEffect(() => {
    getCart()
      .then((c) => {
        if (!c || c.lines.length === 0) {
          router.replace("/cart");
          return;
        }
        setCart(c);
      })
      .catch(() => setError("Не удалось загрузить корзину"))
      .finally(() => setLoading(false));
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;

    if (!name.trim() || !phone.trim()) {
      setError("Укажите имя и телефон");
      return;
    }
    if (delivery === "courier" && !address.trim()) {
      setError("Укажите адрес доставки");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const order = await placeOrder({
        customer_name: name.trim(),
        customer_phone: phone.trim(),
        customer_email: email.trim() || undefined,
        delivery_method: delivery,
        delivery_address: delivery === "courier" ? address.trim() : "",
        payment_method: payment,
        comment: comment.trim() || undefined,
      });
      // Сохраняем данные заказа в sessionStorage для thanks-страницы (GET
      // /api/orders/{number}/ требует аутентификации, а гость — не авторизован).
      try {
        sessionStorage.setItem(
          `order_${order.order_number}`,
          JSON.stringify(order),
        );
      } catch {
        // Если sessionStorage недоступен, redirect всё равно сработает.
      }
      router.push(`/order/${order.order_number}/thanks`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка при оформлении");
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </div>
      </main>
    );
  }

  if (!cart) return null;

  const inputClass =
    "w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none";

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="mb-6 font-display text-3xl font-semibold uppercase tracking-wide text-ink">
        Оформление заказа
      </h1>

      {error && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Контактные данные */}
        <fieldset className="space-y-3 rounded-lg border border-line bg-surface p-5">
          <legend className="px-2 font-display text-lg font-semibold uppercase text-ink">
            Контактные данные
          </legend>
          <div>
            <label htmlFor="name" className="mb-1 block text-sm text-ink-2">
              Имя *
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className={inputClass}
              placeholder="Иван Иванов"
            />
          </div>
          <div>
            <label htmlFor="phone" className="mb-1 block text-sm text-ink-2">
              Телефон *
            </label>
            <input
              id="phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
              className={inputClass}
              placeholder="+7 (___) ___-__-__"
            />
          </div>
          <div>
            <label htmlFor="email" className="mb-1 block text-sm text-ink-2">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              placeholder="ivan@example.com"
            />
          </div>
        </fieldset>

        {/* Доставка */}
        <fieldset className="space-y-3 rounded-lg border border-line bg-surface p-5">
          <legend className="px-2 font-display text-lg font-semibold uppercase text-ink">
            Способ доставки
          </legend>
          <label className="flex cursor-pointer items-center gap-3 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent">
            <input
              type="radio"
              name="delivery"
              value="courier"
              checked={delivery === "courier"}
              onChange={() => setDelivery("courier")}
              className="accent-accent"
            />
            <span className="text-sm text-ink">Курьер</span>
          </label>
          <label className="flex cursor-pointer items-center gap-3 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent">
            <input
              type="radio"
              name="delivery"
              value="pickup"
              checked={delivery === "pickup"}
              onChange={() => setDelivery("pickup")}
              className="accent-accent"
            />
            <span className="text-sm text-ink">Самовывоз</span>
          </label>
          {delivery === "courier" && (
            <div>
              <label
                htmlFor="address"
                className="mb-1 block text-sm text-ink-2"
              >
                Адрес доставки *
              </label>
              <input
                id="address"
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                required
                className={inputClass}
                placeholder="Город, улица, дом, квартира"
              />
            </div>
          )}
        </fieldset>

        {/* Оплата */}
        <fieldset className="space-y-3 rounded-lg border border-line bg-surface p-5">
          <legend className="px-2 font-display text-lg font-semibold uppercase text-ink">
            Способ оплаты
          </legend>
          <label className="flex cursor-pointer items-center gap-3 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent">
            <input
              type="radio"
              name="payment"
              value="online"
              checked={payment === "online"}
              onChange={() => setPayment("online")}
              className="accent-accent"
            />
            <span className="text-sm text-ink">Онлайн-оплата</span>
          </label>
          <label className="flex cursor-pointer items-center gap-3 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent">
            <input
              type="radio"
              name="payment"
              value="invoice"
              checked={payment === "invoice"}
              onChange={() => setPayment("invoice")}
              className="accent-accent"
            />
            <span className="text-sm text-ink">Счёт для организации (B2B)</span>
          </label>
        </fieldset>

        {/* Комментарий */}
        <div className="rounded-lg border border-line bg-surface p-5">
          <label htmlFor="comment" className="mb-1 block text-sm text-ink-2">
            Комментарий к заказу
          </label>
          <textarea
            id="comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={3}
            className={`${inputClass} resize-none`}
            placeholder="Дополнительные пожелания..."
          />
        </div>

        {/* Состав заказа */}
        <div className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-3 font-display text-lg font-semibold uppercase text-ink">
            Состав заказа
          </h2>
          <div className="space-y-2">
            {cart.lines.map((line) => (
              <div
                key={line.id}
                className="flex items-center justify-between gap-2 text-sm"
              >
                <span className="min-w-0 flex-1 truncate text-ink-2">
                  {line.name}
                  <span className="text-ink-3"> x {line.quantity}</span>
                </span>
                <span className="shrink-0 font-display font-semibold text-ink">
                  {line.line_total
                    ? formatPrice(Number(line.line_total))
                    : "—"}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
            <span className="text-lg text-ink-2">Итого:</span>
            <span className="font-display text-2xl font-bold text-ink">
              {formatPrice(Number(cart.total))}
            </span>
          </div>
        </div>

        {/* Кнопка оформления */}
        <div className="flex justify-end">
          <Button
            type="submit"
            variant="accent"
            disabled={submitting}
            className="px-8 py-2.5 text-base"
          >
            {submitting ? "Оформляем..." : "Оформить заказ"}
          </Button>
        </div>
      </form>
    </main>
  );
}
