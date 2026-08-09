"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/states";
import { useCart } from "@/components/cart/CartProvider";
import { PromoCodeField } from "@/components/cart/PromoCodeField";
import { ApiError } from "@/lib/api";
import {
  getDeliverySlots,
  getDeliveryZones,
  type DeliverySlotOption,
  type DeliveryZoneOption,
} from "@/lib/delivery";
import { formatPrice, formatSlotDay } from "@/lib/format";
import { placeOrder, startOrderPayment } from "@/lib/orders";
import {
  isLegalEntityInn,
  isValidEmail,
  isValidInn,
  isValidKpp,
  isValidPhone,
  normalizePhone,
} from "@/lib/validation";
import { stashOrder } from "@/lib/order-storage";
import { SITE } from "@/lib/site";
import { composeAddress, validateAddress } from "@/lib/delivery-address";

type CustomerType = "b2c" | "b2b";
type DeliveryMethod = "courier" | "pickup";
type PaymentMethod = "online" | "invoice";

// #574: высота полей — как в дизайн-системе (components/ui/input.tsx): 44px на
// мобильном (тач-таргет), компактнее на desktop. Раньше py-2 давал ~36px и все
// селекты checkout (зона, интервал доставки) были ниже минимума для пальца.
const inputClass =
  "h-11 w-full rounded-md border border-line bg-canvas px-3 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none sm:h-9";

export default function CheckoutPage() {
  const router = useRouter();
  const { cart, loading, total, refresh } = useCart();

  const [submitting, setSubmitting] = useState(false);
  // Фаза отправки: «оформляем» и «переходим к оплате» — разные ожидания. Второе
  // заканчивается уходом на сайт кассы, и человек должен понимать, куда его ведут.
  const [phase, setPhase] = useState<"idle" | "placing" | "paying">("idle");
  const [error, setError] = useState<string | null>(null);
  // Anti-double-submit: ref не зависит от ре-рендера и закрывает гонку «двух кликов подряд».
  const inFlight = useRef(false);
  // Заказ уже оформлен: страница доживает до перехода на «Спасибо», и опустевшую
  // корзину нельзя трактовать как повод вернуть человека в /cart (DRF-950).
  const placed = useRef(false);
  const errorRef = useRef<HTMLDivElement | null>(null);

  // #574: подвести пользователя к тексту ошибки — она рендерится над формой,
  // а нажимают кнопку внизу. Без этого сабмит выглядел как «ничего не произошло».
  useEffect(() => {
    if (!error) return;
    // scrollIntoView отсутствует в jsdom — вызываем опционально.
    errorRef.current?.scrollIntoView?.({ block: "center", behavior: "smooth" });
    errorRef.current?.focus();
  }, [error]);

  const [customerType, setCustomerType] = useState<CustomerType>("b2c");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [inn, setInn] = useState("");
  const [kpp, setKpp] = useState("");
  const [legalAddress, setLegalAddress] = useState("");
  // Адрес — по частям, как на службах доставки. Одно поле «Адрес доставки»
  // покупатели заполняли обрывками («Пен», «Молокова»), и курьеру ехать было
  // некуда. Разложенные поля подсказывают, чего не хватает, ещё до отправки.
  // На сервер уходит по-прежнему одна строка (см. composeAddress).
  const [city, setCity] = useState<string>(SITE.region);
  const [street, setStreet] = useState("");
  const [house, setHouse] = useState("");
  const [flat, setFlat] = useState("");
  const [entrance, setEntrance] = useState("");
  const [floor, setFloor] = useState("");
  const [comment, setComment] = useState("");
  const [delivery, setDelivery] = useState<DeliveryMethod>("courier");

  const isB2B = customerType === "b2b";
  const addressParts = { city, street, house, flat, entrance, floor };

  // Способ оплаты не хранится в состоянии: бэк (CreateOrderSerializer.validate) допускает
  // ровно одну связку — b2c → online, b2b → invoice, любая другая комбинация даёт 400.
  // Раньше payment был независимым состоянием с дефолтом "online", поэтому B2B-заказ
  // гарантированно отклонялся. Выводим значение из типа покупателя.
  const payment: PaymentMethod = isB2B ? "invoice" : "online";

  // #571: серверный промо-breakdown. Суммы здесь — только превью; авторитетный
  // расчёт (включая free_delivery-код) делает place_order.
  const promoDiscount = Number(cart?.items_discount_total ?? 0) || 0;
  const goodsPayable = cart ? Number(cart.grand_total) || total : total;
  const hasFreeDeliveryCode = Boolean(
    cart?.applied_promotions?.some((a) => a.discount_type === "free_delivery"),
  );
  // #574: суммы форматируем в валюте корзины. Раньше formatPrice звался без
  // второго аргумента и любой заказ подписывался «₽», хотя в кабинете валюта
  // уже передавалась — один и тот же заказ выглядел по-разному.
  const currency = cart?.currency || "RUB";

  // Зоны доставки (аудит №5): без delivery_zone сервер не считает стоимость
  // (заказ уходил с доставкой 0 ₽ и заниженным итогом). Слаг выбранной зоны
  // уходит в POST /api/orders; стоимость из списка — только предпросмотр,
  // сервер (quote_for_order) пересчитывает сам.
  // #574: null — ещё грузим. Раньше стартовое [] было неотличимо от «зон нет»,
  // и на первую отрисовку блок выбора зоны просто отсутствовал без объяснения.
  const [zones, setZones] = useState<DeliveryZoneOption[] | null>(null);
  const [zonesFailed, setZonesFailed] = useState(false);
  const [zoneSlug, setZoneSlug] = useState("");

  useEffect(() => {
    let active = true;
    getDeliveryZones(goodsPayable).then((data) => {
      if (!active) return;
      if (data === "error") {
        setZonesFailed(true);
        setZones([]);
      } else {
        setZonesFailed(false);
        setZones(data);
      }
    });
    return () => {
      active = false;
    };
  }, [goodsPayable]);

  const courierZones = useMemo(() => (zones ?? []).filter((z) => z.type === "courier"), [zones]);
  const selectedZone = courierZones.find((z) => z.zone === zoneSlug) ?? null;

  // Предпросмотр итога: товары после скидок + доставка выбранной зоны.
  // Авторитетную сумму считает сервер при оформлении (см. подпись под итогом).
  const previewDeliveryCost =
    !isB2B &&
    delivery === "courier" &&
    selectedZone &&
    !selectedZone.free_delivery &&
    !hasFreeDeliveryCode
      ? Number(selectedZone.cost) || 0
      : 0;
  const previewTotal = goodsPayable + previewDeliveryCost;

  // #569: слоты доставки — только B2C + курьер. Пустой список = пикер скрыт,
  // заказ уходит без слота (менеджер согласует время). Сервер перепроверит
  // слот авторитетно при оформлении.
  // #574: null — загрузка. Раньше стартовое [] показывало «Доступных интервалов
  // доставки нет» ещё до ответа сервера, то есть экран врал на первую отрисовку.
  const [slots, setSlots] = useState<DeliverySlotOption[] | null>(null);
  const [slotsFailed, setSlotsFailed] = useState(false);
  const [slotId, setSlotId] = useState<number | null>(null);

  useEffect(() => {
    // Для B2B/самовывоза пикер не рендерится и slot_id не уходит в payload —
    // список можно не чистить, только не запрашивать.
    if (isB2B || delivery !== "courier") return;
    let active = true;
    // Список НЕ сбрасываем в null при смене зоны: пока едет новый ответ,
    // требование «выберите интервал» должно оставаться в силе, иначе между
    // сменой зоны и ответом сервера заказ уходил бы без слота.
    getDeliverySlots(zoneSlug || undefined).then((data) => {
      if (!active) return;
      if (data === "error") {
        setSlotsFailed(true);
        setSlots([]);
      } else {
        setSlotsFailed(false);
        setSlots(data);
      }
    });
    return () => {
      active = false;
    };
  }, [isB2B, delivery, zoneSlug]);

  const slotsByDate = useMemo(() => {
    const groups = new Map<string, DeliverySlotOption[]>();
    for (const slot of slots ?? []) {
      const list = groups.get(slot.date) ?? [];
      list.push(slot);
      groups.set(slot.date, list);
    }
    return [...groups.entries()];
  }, [slots]);

  // Пустую корзину оформлять нечего — уводим на /cart (после загрузки снимка).
  //
  // DRF-950: но ровно так же корзина выглядит сразу ПОСЛЕ успешного оформления —
  // бэкенд закрывает её вместе с созданием заказа. Раньше сторож срабатывал на
  // этот момент и уводил покупателя в пустую корзину вместо страницы «Спасибо»:
  // заказ создан, деньги ждут оплаты, а человек видит «Корзина пуста» и жмёт
  // «Оформить» снова — второй раз уже с ошибкой от сервера. Флаг placed
  // отличает «корзина опустела, потому что заказ оформлен» от «зашли с пустой».
  useEffect(() => {
    if (placed.current) return;
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

    if (!name.trim()) return setError("Укажите имя.");
    if (!isValidPhone(phone)) return setError("Укажите корректный телефон.");
    if (email.trim() && !isValidEmail(email)) return setError("Укажите корректный e-mail.");
    // B2B-реквизиты зеркалят validate_b2b_requisites (apps/orders/invoice.py): без них
    // бэк отвечает 400, а заполнить их в форме было негде — B2B-заказ не оформлялся вовсе.
    if (isB2B) {
      if (!companyName.trim()) return setError("Укажите название организации.");
      if (!isValidInn(inn)) return setError("ИНН должен содержать 10 или 12 цифр.");
      if (isLegalEntityInn(inn) && !kpp.trim()) {
        return setError("КПП обязателен для юридического лица (ИНН из 10 цифр).");
      }
      if (kpp.trim() && !isValidKpp(kpp)) return setError("КПП должен содержать 9 цифр.");
      if (!legalAddress.trim()) return setError("Укажите юридический адрес.");
      if (!email.trim()) return setError("Укажите e-mail — на него придёт счёт.");
    }
    // #558: для юрлиц доставки нет (самовывоз) — адрес и зона не запрашиваются.
    if (!isB2B && delivery === "courier") {
      const addressError = validateAddress(addressParts);
      if (addressError) return setError(addressError);
    }
    // Зона обязательна, только если список зон вообще доступен: при недоступном
    // справочнике заказ создаётся без зоны (менеджер уточнит) — как раньше.
    if (!isB2B && delivery === "courier" && courierZones.length > 0 && !zoneSlug) {
      return setError("Выберите зону доставки.");
    }
    // #569: слот обязателен, только если слоты вообще есть — пустой справочник
    // не должен останавливать курьерские заказы.
    if (!isB2B && delivery === "courier" && (slots?.length ?? 0) > 0 && !slotId) {
      return setError("Выберите дату и время доставки.");
    }

    inFlight.current = true;
    setSubmitting(true);
    setPhase("placing");
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
        delivery_address:
          !isB2B && delivery === "courier" ? composeAddress(addressParts) : "",
        delivery_zone: !isB2B && delivery === "courier" ? zoneSlug : "",
        delivery_slot_id: !isB2B && delivery === "courier" ? slotId : null,
        payment_method: payment,
        comment: comment.trim(),
      });
      // Снимок заказа сохраняем для /thanks: GET /api/orders/{number}/ гостю недоступен.
      stashOrder(order);
      // Заказ создан — дальше корзина обязана опустеть, и это НЕ повод считать её
      // брошенной. Флаг ставим до всего остального, иначе сторож пустой корзины
      // успевает увести на /cart (DRF-950).
      placed.current = true;

      // Онлайн-оплата: заказ уже сохранён, дальше ведём в кассу. Любая неудача
      // здесь — не потеря заказа: страница «Спасибо» покажет его в статусе
      // «ожидает оплаты» с кнопкой повтора, поэтому переход туда выполняется
      // в обоих случаях.
      if (payment === "online") {
        setPhase("paying");
        try {
          const started = await startOrderPayment(order.order_number, order.access_token);
          if (started.confirmation_url) {
            window.location.assign(started.confirmation_url);
            return;
          }
        } catch {
          // Касса недоступна или выключена — молча уходим на страницу заказа.
        }
      }
      router.push(`/order/${order.order_number}/thanks`);
      // Счётчик в шапке обновляем следом, уже не блокируя переход.
      void refresh();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Не удалось оформить заказ. Попробуйте ещё раз.",
      );
      // #569: заказ со слотом не прошёл (чаще всего «время уже занято») —
      // обновляем справочник и сбрасываем выбор, текст ошибки уже от сервера.
      if (err instanceof ApiError && !isB2B && delivery === "courier" && slotId) {
        setSlotId(null);
        getDeliverySlots(zoneSlug || undefined).then((data) => {
          setSlotsFailed(data === "error");
          setSlots(data === "error" ? [] : data);
        });
      }
      inFlight.current = false;
      setSubmitting(false);
      setPhase("idle");
    }
  };

  if (loading || !cart || cart.lines.length === 0) {
    return (
      <main className="mx-auto min-h-[60vh] w-full max-w-[1480px] px-4 py-10 sm:px-6 lg:px-8">
        <LoadingState label="Готовим оформление заказа…" />
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-[1480px] px-4 pb-32 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-7">
      <nav
        aria-label="Хлебные крошки"
        className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex"
      >
        <Link href="/" className="hover:text-accent">Главная</Link>
        <span aria-hidden>›</span>
        <Link href="/cart" className="hover:text-accent">Корзина</Link>
        <span aria-hidden>›</span>
        <span>Оформление заказа</span>
      </nav>
      <h1 className="font-display text-2xl font-semibold text-ink lg:text-[30px]">
        Оформление заказа
      </h1>
      <ol className="mb-5 mt-4 flex max-w-2xl items-center text-xs font-semibold sm:text-sm">
        <li className="flex items-center gap-2 text-accent">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-accent text-accent-ink">✓</span>
          Корзина
        </li>
        <li className="mx-3 h-px flex-1 bg-accent sm:mx-5" aria-hidden />
        <li className="flex items-center gap-2 text-accent">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-accent text-accent-ink">2</span>
          Оформление
        </li>
        <li className="mx-3 h-px flex-1 bg-line sm:mx-5" aria-hidden />
        <li className="flex items-center gap-2 whitespace-nowrap text-ink-3">
          <span className="grid h-6 w-6 place-items-center rounded-full border border-line">3</span>
          Заказ принят
        </li>
      </ol>

      {/* #574: role="alert" + фокус. Баннер живёт вверху страницы, а кнопка
          сабмита — внизу: на мобильном ошибка оказывалась вне вьюпорта, и клик
          выглядел как «кнопка молчит». */}
      {error && (
        <div
          ref={errorRef}
          role="alert"
          tabIndex={-1}
          className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger outline-none"
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="space-y-5">
        <fieldset className="space-y-3 rounded-lg border border-line bg-surface p-5">
          <legend className="px-2 font-display text-lg font-semibold uppercase text-ink">
            Покупатель
          </legend>
          {/* #574: flex-wrap + min-w — на 320px «Физическое лицо» больше не жмётся. */}
          <div className="flex flex-wrap gap-3">
            {(
              [
                ["b2c", "Физическое лицо"],
                ["b2b", "Организация"],
              ] as const
            ).map(([value, label]) => (
              <label
                key={value}
                className="flex min-w-[9rem] flex-1 cursor-pointer items-center gap-2 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent"
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
              {zones === null && (
                <p className="text-xs text-ink-3" role="status">
                  Загружаем зоны доставки…
                </p>
              )}
              {zonesFailed && (
                <p
                  role="alert"
                  className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
                >
                  Не удалось загрузить зоны доставки. Обновите страницу — или оформите заказ
                  сейчас, менеджер уточнит стоимость доставки.
                </p>
              )}
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
                    Стоимость доставки войдёт в итог заказа.
                  </p>
                </div>
              )}
              {slots === null ? (
                <p className="text-xs text-ink-3" role="status">
                  Загружаем свободные интервалы…
                </p>
              ) : slotsFailed ? (
                <p
                  role="alert"
                  className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
                >
                  Не удалось загрузить интервалы доставки. Обновите страницу — или оформите
                  заказ сейчас, менеджер согласует время.
                </p>
              ) : slots.length > 0 ? (
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
                      <optgroup key={date} label={formatSlotDay(date)}>
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
              {/* Адрес по частям. Город и улица занимают строку целиком —
                  названия длинные; дом, квартира, подъезд и этаж короткие и
                  становятся в один ряд, на телефоне — по два в строке. */}
              <fieldset className="space-y-3">
                <legend className="mb-1 text-sm font-medium text-ink">Адрес доставки</legend>
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
                  <div>
                    <label htmlFor="city" className="mb-1 block text-sm text-ink-2">
                      Город *
                    </label>
                    <input
                      id="city"
                      type="text"
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      className={inputClass}
                      placeholder="Пенза"
                      autoComplete="address-level2"
                    />
                  </div>
                  <div>
                    <label htmlFor="street" className="mb-1 block text-sm text-ink-2">
                      Улица *
                    </label>
                    <input
                      id="street"
                      type="text"
                      value={street}
                      onChange={(e) => setStreet(e.target.value)}
                      className={inputClass}
                      placeholder="1-й Онежский проезд"
                      autoComplete="address-line1"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div>
                    <label htmlFor="house" className="mb-1 block text-sm text-ink-2">
                      Дом *
                    </label>
                    <input
                      id="house"
                      type="text"
                      value={house}
                      onChange={(e) => setHouse(e.target.value)}
                      className={inputClass}
                      placeholder="12"
                      autoComplete="address-line2"
                    />
                  </div>
                  <div>
                    <label htmlFor="flat" className="mb-1 block text-sm text-ink-2">
                      Кв./офис
                    </label>
                    <input
                      id="flat"
                      type="text"
                      value={flat}
                      onChange={(e) => setFlat(e.target.value)}
                      className={inputClass}
                      placeholder="45"
                    />
                  </div>
                  <div>
                    <label htmlFor="entrance" className="mb-1 block text-sm text-ink-2">
                      Подъезд
                    </label>
                    <input
                      id="entrance"
                      type="text"
                      value={entrance}
                      onChange={(e) => setEntrance(e.target.value)}
                      className={inputClass}
                      placeholder="2"
                    />
                  </div>
                  <div>
                    <label htmlFor="floor" className="mb-1 block text-sm text-ink-2">
                      Этаж
                    </label>
                    <input
                      id="floor"
                      type="text"
                      value={floor}
                      onChange={(e) => setFloor(e.target.value)}
                      className={inputClass}
                      placeholder="3"
                    />
                  </div>
                </div>
                {/* Собранная строка — то, что увидит курьер и что уедет в 1С.
                    Показываем сразу: так опечатка ловится до оформления. */}
                {(street.trim() || house.trim()) && (
                  <p className="rounded-md bg-raised px-3 py-2 text-xs leading-5 text-ink-2">
                    Курьеру: {composeAddress(addressParts)}
                  </p>
                )}
              </fieldset>
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

          </div>

          <aside className="space-y-4 lg:sticky lg:top-24">
        <div className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-3 font-display text-lg font-semibold uppercase text-ink">
            Ваш заказ
          </h2>
          <div className="mb-4">
            <PromoCodeField />
          </div>
          <div className="space-y-2">
            {cart.lines.map((line) => (
              <div key={line.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0 flex-1 truncate text-ink-2">
                  {line.name}
                  <span className="text-ink-3"> × {line.quantity}</span>
                </span>
                <span className="shrink-0 font-display font-semibold text-ink">
                  {line.line_total ? formatPrice(Number(line.line_total), currency) : "—"}
                </span>
              </div>
            ))}
          </div>
          {promoDiscount > 0 && (
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3 text-sm">
              <span className="min-w-0 flex-1 truncate text-ink-2">Скидка по акциям:</span>
              <span className="shrink-0 font-display font-semibold text-accent">
                − {formatPrice(promoDiscount, currency)}
              </span>
            </div>
          )}
          {/* #574: строка доставки показывается всегда (кроме B2B — у юрлиц
              доставки нет, #558). Раньше она исчезала до выбора зоны, и итог
              молча равнялся сумме товаров без единого намёка на доставку. */}
          {!isB2B && (
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3 text-sm">
              <span className="min-w-0 flex-1 truncate text-ink-2">
                {delivery === "pickup"
                  ? "Самовывоз со склада:"
                  : selectedZone
                    ? `Доставка (${selectedZone.name}):`
                    : "Доставка:"}
              </span>
              <span className="shrink-0 font-display font-semibold text-ink">
                {delivery === "pickup"
                  ? "бесплатно"
                  : !selectedZone
                    ? "рассчитается после выбора зоны"
                    : selectedZone.free_delivery
                      ? "бесплатно"
                      : hasFreeDeliveryCode
                        ? "бесплатно (промокод)"
                        : formatPrice(Number(selectedZone.cost), currency)}
              </span>
            </div>
          )}
          {/* #574: «Предварительный итог» — та же формулировка, что в детали заказа.
              Итоговую сумму считает сервер (quote_for_order внутри транзакции,
              ADR-0012); здесь только предпросмотр, и подпись это признаёт. */}
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3">
            <span className="min-w-0 flex-1 text-lg text-ink-2">Предварительный итог:</span>
            <span className="shrink-0 font-display text-2xl font-bold text-ink">
              {mixedCurrencies ? "—" : formatPrice(previewTotal, currency)}
            </span>
          </div>
          {mixedCurrencies ? (
            <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
              В корзине товары в разных валютах — итог не считается. Вернитесь в корзину и
              оформите их отдельными заказами.
            </p>
          ) : (
            <p className="mt-1 text-right text-[11px] text-ink-3">
              Окончательную сумму, включая доставку, считает сервер при оформлении.
            </p>
          )}
          {/* #574: до оформления резерва ещё нет, точное «до HH:MM» появится на
              «Спасибо» и в кабинете. Здесь — предупреждение без числа: срок
              резерва задаёт бэк, хардкодить его на фронте нельзя. */}
          {!isB2B && (
            <p className="mt-3 rounded-md border border-line bg-raised px-3 py-2 text-xs text-ink-2">
              После оформления товар зарезервируем за вами до оплаты — точное время покажем
              на странице заказа.
            </p>
          )}
        </div>

        <div className="fixed inset-x-0 bottom-0 z-50 flex h-[72px] items-center justify-between gap-3 border-t border-line bg-surface px-4 shadow-[0_-8px_24px_rgba(20,24,27,0.08)] lg:static lg:block lg:h-auto lg:border-0 lg:bg-transparent lg:px-0 lg:shadow-none">
          <div className="lg:hidden">
            <p className="text-[11px] text-ink-3">Предварительный итог</p>
            <p className="text-lg font-bold text-ink">
              {mixedCurrencies ? "—" : formatPrice(previewTotal, currency)}
            </p>
          </div>
          <Button
            type="submit"
            variant="accent"
            disabled={submitting || mixedCurrencies}
            className="h-11 px-5 lg:h-12 lg:w-full lg:px-8 lg:text-base"
          >
            {phase === "paying"
              ? "Переходим к оплате…"
              : submitting
                ? "Оформляем…"
                : "Оформить заказ"}
          </Button>
        </div>
          </aside>
        </div>
      </form>
    </main>
  );
}
