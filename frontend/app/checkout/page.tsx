"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";
import {
  getDeliverySlots,
  getDeliveryZones,
  type DeliverySlotOption,
  type DeliveryZoneOption,
} from "@/lib/delivery";
import { formatPrice } from "@/lib/format";
import { placeOrder } from "@/lib/orders";
import {
  isLegalEntityInn,
  isValidEmail,
  isValidInn,
  isValidKpp,
  isValidPhone,
  normalizePhone,
} from "@/lib/validation";
import { stashOrder } from "@/lib/order-storage";

type CustomerType = "b2c" | "b2b";
type DeliveryMethod = "courier" | "pickup";
type PaymentMethod = "online" | "invoice";

const inputClass =
  "w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none";

// #569: подпись группы слотов: «вт, 21 июля».
function formatSlotDate(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("ru-RU", {
    weekday: "short",
    day: "numeric",
    month: "long",
  });
}

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
  const [kpp, setKpp] = useState("");
  const [legalAddress, setLegalAddress] = useState("");
  const [address, setAddress] = useState("");
  const [comment, setComment] = useState("");
  const [delivery, setDelivery] = useState<DeliveryMethod>("courier");

  const isB2B = customerType === "b2b";

  // Способ оплаты не хранится в состоянии: бэк (CreateOrderSerializer.validate) допускает
  // ровно одну связку — b2c → online, b2b → invoice, любая другая комбинация даёт 400.
  // Раньше payment был независимым состоянием с дефолтом "online", поэтому B2B-заказ
  // гарантированно отклонялся. Выводим значение из типа покупателя.
  const payment: PaymentMethod = isB2B ? "invoice" : "online";

  // Зоны доставки (аудит №5): без delivery_zone сервер не считает стоимость
  // (заказ уходил с доставкой 0 ₽ и заниженным итогом). Слаг выбранной зоны
  // уходит в POST /api/orders; стоимость из списка — только предпросмотр,
  // сервер (quote_for_order) пересчитывает сам.
  const [zones, setZones] = useState<DeliveryZoneOption[]>([]);
  const [zoneSlug, setZoneSlug] = useState("");

  useEffect(() => {
    let active = true;
    getDeliveryZones(total).then((data) => {
      if (active) setZones(data);
    });
    return () => {
      active = false;
    };
  }, [total]);

  const courierZones = useMemo(() => zones.filter((z) => z.type === "courier"), [zones]);
  const selectedZone = courierZones.find((z) => z.zone === zoneSlug) ?? null;

  // #569: слоты доставки — только B2C + курьер. Пустой список = пикер скрыт,
  // заказ уходит без слота (менеджер согласует время). Сервер перепроверит
  // слот авторитетно при оформлении.
  const [slots, setSlots] = useState<DeliverySlotOption[]>([]);
  const [slotId, setSlotId] = useState<number | null>(null);

  useEffect(() => {
    // Для B2B/самовывоза пикер не рендерится и slot_id не уходит в payload —
    // список можно не чистить, только не запрашивать.
    if (isB2B || delivery !== "courier") return;
    let active = true;
    getDeliverySlots(zoneSlug || undefined).then((data) => {
      if (active) setSlots(data);
    });
    return () => {
      active = false;
    };
  }, [isB2B, delivery, zoneSlug]);

  const slotsByDate = useMemo(() => {
    const groups = new Map<string, DeliverySlotOption[]>();
    for (const slot of slots) {
      const list = groups.get(slot.date) ?? [];
      list.push(slot);
      groups.set(slot.date, list);
    }
    return [...groups.entries()];
  }, [slots]);

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
    // B2B-реквизиты зеркалят validate_b2b_requisites (apps/orders/invoice.py): без них
    // бэк отвечает 400, а заполнить их в форме было негде — B2B-заказ не оформлялся вовсе.
    if (isB2B) {
      if (!companyName.trim()) return setError("Укажите название организации");
      if (!isValidInn(inn)) return setError("ИНН должен содержать 10 или 12 цифр");
      if (isLegalEntityInn(inn) && !kpp.trim()) {
        return setError("КПП обязателен для юридического лица (ИНН из 10 цифр)");
      }
      if (kpp.trim() && !isValidKpp(kpp)) return setError("КПП должен содержать 9 цифр");
      if (!legalAddress.trim()) return setError("Укажите юридический адрес");
      if (!email.trim()) return setError("Укажите e-mail — на него придёт счёт");
    }
    // #558: для юрлиц доставки нет (самовывоз) — адрес и зона не запрашиваются.
    if (!isB2B && delivery === "courier" && !address.trim()) {
      return setError("Укажите адрес доставки");
    }
    // Зона обязательна, только если список зон вообще доступен: при недоступном
    // справочнике заказ создаётся без зоны (менеджер уточнит) — как раньше.
    if (!isB2B && delivery === "courier" && courierZones.length > 0 && !zoneSlug) {
      return setError("Выберите зону доставки");
    }
    // #569: слот обязателен, только если слоты вообще есть — пустой справочник
    // не должен останавливать курьерские заказы.
    if (!isB2B && delivery === "courier" && slots.length > 0 && !slotId) {
      return setError("Выберите дату и время доставки");
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
        company_name: isB2B ? companyName.trim() : "",
        inn: isB2B ? inn.trim() : "",
        kpp: isB2B ? kpp.trim() : "",
        legal_address: isB2B ? legalAddress.trim() : "",
        delivery_method: isB2B ? "pickup" : delivery,
        delivery_address: !isB2B && delivery === "courier" ? address.trim() : "",
        delivery_zone: !isB2B && delivery === "courier" ? zoneSlug : "",
        delivery_slot_id: !isB2B && delivery === "courier" ? slotId : null,
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
      // #569: заказ со слотом не прошёл (чаще всего «время уже занято») —
      // обновляем справочник и сбрасываем выбор, текст ошибки уже от сервера.
      if (err instanceof ApiError && !isB2B && delivery === "courier" && slotId) {
        setSlotId(null);
        getDeliverySlots(zoneSlug || undefined).then(setSlots);
      }
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
                  onChange={() => {
                    setCustomerType(value);
                    // #569: у B2B слотов нет — выбранный слот неактуален.
                    setSlotId(null);
                  }}
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
              E-mail {isB2B ? "*" : ""}
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
                  ИНН *
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
                <p className="mt-1 text-xs text-ink-3">10 цифр — организация, 12 — ИП.</p>
              </div>
              {/* КПП обязателен только для юрлица (ИНН 10 цифр); у ИП его нет. */}
              <div>
                <label htmlFor="kpp" className="mb-1 block text-sm text-ink-2">
                  КПП {isLegalEntityInn(inn) ? "*" : ""}
                </label>
                <input
                  id="kpp"
                  type="text"
                  inputMode="numeric"
                  value={kpp}
                  onChange={(e) => setKpp(e.target.value)}
                  className={inputClass}
                  placeholder="770001001"
                />
              </div>
              <div>
                <label htmlFor="legalAddress" className="mb-1 block text-sm text-ink-2">
                  Юридический адрес *
                </label>
                <input
                  id="legalAddress"
                  type="text"
                  value={legalAddress}
                  onChange={(e) => setLegalAddress(e.target.value)}
                  className={inputClass}
                  placeholder="123456, г. Москва, ул. Ленина, д. 1, оф. 2"
                />
              </div>
            </>
          )}
        </fieldset>

        {/* #558 (Wave 1): для юрлиц доставки нет — блок скрыт, заказ уходит самовывозом,
            счёт формируется только на товары. Бэк отклонит courier для B2B в любом случае. */}
        {isB2B ? (
          <div className="rounded-lg border border-line bg-surface p-5">
            <h2 className="font-display text-lg font-semibold uppercase text-ink">Получение</h2>
            <p className="mt-2 text-sm text-ink-2">
              Для юридических лиц — самовывоз со склада. Счёт формируется только на товары;
              доставка для организаций появится позже.
            </p>
          </div>
        ) : (
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
              onChange={() => {
                setDelivery("courier");
                // #569: возврат к курьеру начинается с чистого выбора слота.
                setSlotId(null);
              }}
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
              onChange={() => {
                setDelivery("pickup");
                // #569: самовывозу слот не нужен — устаревший id не должен
                // попасть в payload (бэк ответит 400).
                setSlotId(null);
              }}
              className="accent-accent"
            />
            <span className="text-sm text-ink">Самовывоз</span>
          </label>
          {delivery === "courier" && (
            <>
              {courierZones.length > 0 && (
                <div>
                  <label htmlFor="deliveryZone" className="mb-1 block text-sm text-ink-2">
                    Зона доставки *
                  </label>
                  <select
                    id="deliveryZone"
                    value={zoneSlug}
                    onChange={(e) => {
                      setZoneSlug(e.target.value);
                      // #569: зональные слоты другой зоны несовместимы.
                      setSlotId(null);
                    }}
                    className={inputClass}
                  >
                    <option value="">— выберите зону —</option>
                    {courierZones.map((z) => (
                      <option key={z.zone} value={z.zone}>
                        {z.name}
                        {z.free_delivery
                          ? " — бесплатно"
                          : Number(z.cost) > 0
                            ? ` — ${formatPrice(Number(z.cost))}`
                            : ""}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1 text-xs text-ink-3">
                    Стоимость доставки рассчитывается сервером и входит в итог заказа.
                  </p>
                </div>
              )}
              {slots.length > 0 ? (
                <div>
                  <label htmlFor="deliverySlot" className="mb-1 block text-sm text-ink-2">
                    Дата и время доставки *
                  </label>
                  <select
                    id="deliverySlot"
                    value={slotId ?? ""}
                    onChange={(e) => setSlotId(e.target.value ? Number(e.target.value) : null)}
                    className={inputClass}
                  >
                    <option value="">— выберите интервал —</option>
                    {slotsByDate.map(([date, daySlots]) => (
                      <optgroup key={date} label={formatSlotDate(date)}>
                        {daySlots.map((slot) => (
                          <option key={slot.id} value={slot.id}>
                            {slot.starts_at}–{slot.ends_at}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
              ) : (
                <p className="text-xs text-ink-3">
                  Доступных интервалов доставки нет — менеджер согласует время после
                  оформления заказа.
                </p>
              )}
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
            </>
          )}
        </fieldset>
        )}

        <fieldset className="space-y-3 rounded-lg border border-line bg-surface p-5">
          <legend className="px-2 font-display text-lg font-semibold uppercase text-ink">
            Способ оплаты
          </legend>
          {/* Способ оплаты определяется типом покупателя (см. вывод payment выше), поэтому
              оба варианта показываем, но заблокированными: правило видно, выбрать нечего. */}
          {(
            [
              ["online", "Онлайн-оплата"],
              ["invoice", "Счёт для организации (B2B)"],
            ] as const
          ).map(([value, label]) => (
            <label
              key={value}
              className={`flex items-center gap-3 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent ${
                payment === value ? "" : "opacity-50"
              }`}
            >
              <input
                type="radio"
                name="payment"
                value={value}
                checked={payment === value}
                disabled
                readOnly
                className="accent-accent"
              />
              <span className="text-sm text-ink">{label}</span>
            </label>
          ))}
          <p className="text-xs text-ink-3">
            {isB2B
              ? "Заказы организаций оплачиваются только по счёту."
              : "Оплата по счёту доступна только для организаций."}
          </p>
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
          {!isB2B && delivery === "courier" && selectedZone && (
            <div className="mt-3 flex items-center justify-between border-t border-line pt-3 text-sm">
              <span className="text-ink-2">Доставка ({selectedZone.name}):</span>
              <span className="font-display font-semibold text-ink">
                {selectedZone.free_delivery ? "бесплатно" : formatPrice(Number(selectedZone.cost))}
              </span>
            </div>
          )}
          <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
            <span className="text-lg text-ink-2">Итого:</span>
            <span className="font-display text-2xl font-bold text-ink">
              {mixedCurrencies
                ? "—"
                : formatPrice(
                    total +
                      (!isB2B && delivery === "courier" && selectedZone && !selectedZone.free_delivery
                        ? Number(selectedZone.cost) || 0
                        : 0),
                  )}
            </span>
          </div>
          {mixedCurrencies ? (
            <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
              В корзине товары в разных валютах — итог не считается. Вернитесь в корзину и
              оформите их отдельными заказами.
            </p>
          ) : (
            <p className="mt-1 text-right text-[11px] text-ink-3">
              Точный итог (с доставкой) рассчитывает сервер при оформлении.
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
