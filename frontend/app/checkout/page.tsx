"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { placeOrder } from "@/lib/orders";
import { isValidEmail, isValidPhone, normalizePhone } from "@/lib/validation";
import { stashOrder } from "@/lib/order-storage";

type CustomerType = "b2c" | "b2b";
type DeliveryMethod = "courier" | "pickup";
type PaymentMethod = "online" | "invoice";

const inputClass =
  "w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none";

export default function CheckoutPage() {
  const router = useRouter();
  const { cart, loading, total, refresh } = useCart();

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Anti-double-submit: ref не зависит от ре-рендера и закрывает гонку «двух кликов подряд».
  const inFlight = useRef(false);

  const [customerType, setCustomerType] = useState<CustomerType>("b2c");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [inn, setInn] = useState("");
  const [address, setAddress] = useState("");
  const [comment, setComment] = useState("");
  const [delivery, setDelivery] = useState<DeliveryMethod>("courier");
  const [payment, setPayment] = useState<PaymentMethod>("online");

  // Пустую корзину оформлять нечего — уводим на /cart (после загрузки снимка).
  useEffect(() => {
    if (!loading && (!cart || cart.lines.length === 0)) {
      router.replace("/cart");
    }
  }, [loading, cart, router]);

  // #375: при смешении валют бэк обнуляет total — такой заказ оформлять нельзя
  // (корзина блокирует переход, но прямой заход на /checkout тоже надо закрыть).
  const mixedCurrencies = Boolean(cart?.has_mixed_currencies);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (inFlight.current) return;
    if (mixedCurrencies) {
      return setError(
        "В корзине товары в разных валютах — оформите их отдельными заказами.",
      );
    }

    if (!name.trim()) return setError("Укажите имя");
    if (!isValidPhone(phone)) return setError("Укажите корректный телефон");
    if (email.trim() && !isValidEmail(email)) return setError("Укажите корректный e-mail");
    if (customerType === "b2b" && !companyName.trim()) {
      return setError("Укажите название организации");
    }
    if (delivery === "courier" && !address.trim()) {
      return setError("Укажите адрес доставки");
    }

    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const order = await placeOrder({
        customer_name: name.trim(),
        customer_phone: normalizePhone(phone),
        customer_email: email.trim(),
        customer_type: customerType,
        company_name: customerType === "b2b" ? companyName.trim() : "",
        inn: customerType === "b2b" ? inn.trim() : "",
        delivery_method: delivery,
        delivery_address: delivery === "courier" ? address.trim() : "",
        payment_method: payment,
        comment: comment.trim(),
      });
      // Снимок заказа сохраняем для /thanks: GET /api/orders/{number}/ гостю недоступен.
      stashOrder(order);
      // Корзина после оформления закрыта на бэке — обновляем снимок (счётчик Header → 0).
      await refresh();
      router.push(`/order/${order.order_number}/thanks`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ошибка при оформлении заказа");
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  if (loading || !cart || cart.lines.length === 0) {
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
      <h1 className="mb-6 font-display text-3xl font-semibold uppercase tracking-wide text-ink">
        Оформление заказа
      </h1>

      {error && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6" noValidate>
        <fieldset className="space-y-3 rounded-lg border border-line bg-surface p-5">
          <legend className="px-2 font-display text-lg font-semibold uppercase text-ink">
            Покупатель
          </legend>
          <div className="flex gap-3">
            {(
              [
                ["b2c", "Физическое лицо"],
                ["b2b", "Организация"],
              ] as const
            ).map(([value, label]) => (
              <label
                key={value}
                className="flex flex-1 cursor-pointer items-center gap-2 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent"
              >
                <input
                  type="radio"
                  name="customerType"
                  value={value}
                  checked={customerType === value}
                  onChange={() => setCustomerType(value)}
                  className="accent-accent"
                />
                <span className="text-sm text-ink">{label}</span>
              </label>
            ))}
          </div>

          <div>
            <label htmlFor="name" className="mb-1 block text-sm text-ink-2">
              Имя *
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
              placeholder="Иван Иванов"
              autoComplete="name"
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
              className={inputClass}
              placeholder="+7 (___) ___-__-__"
              autoComplete="tel"
            />
          </div>
          <div>
            <label htmlFor="email" className="mb-1 block text-sm text-ink-2">
              E-mail
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              placeholder="ivan@example.com"
              autoComplete="email"
            />
          </div>

          {customerType === "b2b" && (
            <>
              <div>
                <label htmlFor="company" className="mb-1 block text-sm text-ink-2">
                  Организация *
                </label>
                <input
                  id="company"
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className={inputClass}
                  placeholder="ООО «Ромашка»"
                />
              </div>
              <div>
                <label htmlFor="inn" className="mb-1 block text-sm text-ink-2">
                  ИНН
                </label>
                <input
                  id="inn"
                  type="text"
                  inputMode="numeric"
                  value={inn}
                  onChange={(e) => setInn(e.target.value)}
                  className={inputClass}
                  placeholder="7700000000"
                />
              </div>
            </>
          )}
        </fieldset>

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
              <label htmlFor="address" className="mb-1 block text-sm text-ink-2">
                Адрес доставки *
              </label>
              <input
                id="address"
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className={inputClass}
                placeholder="Город, улица, дом, квартира"
                autoComplete="street-address"
              />
            </div>
          )}
        </fieldset>

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
            placeholder="Дополнительные пожелания…"
          />
        </div>

        <div className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-3 font-display text-lg font-semibold uppercase text-ink">
            Состав заказа
          </h2>
          <div className="space-y-2">
            {cart.lines.map((line) => (
              <div key={line.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0 flex-1 truncate text-ink-2">
                  {line.name}
                  <span className="text-ink-3"> × {line.quantity}</span>
                </span>
                <span className="shrink-0 font-display font-semibold text-ink">
                  {line.line_total ? formatPrice(Number(line.line_total)) : "—"}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
            <span className="text-lg text-ink-2">Итого:</span>
            <span className="font-display text-2xl font-bold text-ink">
              {mixedCurrencies ? "—" : formatPrice(total)}
            </span>
          </div>
          {mixedCurrencies && (
            <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
              В корзине товары в разных валютах — итог не считается. Вернитесь в корзину и
              оформите их отдельными заказами.
            </p>
          )}
        </div>

        <div className="flex justify-end">
          <Button
            type="submit"
            variant="accent"
            disabled={submitting || mixedCurrencies}
            className="px-8 py-2.5 text-base"
          >
            {submitting ? "Оформляем…" : "Оформить заказ"}
          </Button>
        </div>
      </form>
    </main>
  );
}
