// Клиент зон доставки (#54): GET /api/delivery/zones через same-origin BFF.
// Чекаут выбирает зону из этого списка и шлёт её слаг в POST /api/orders —
// сервер (quote_for_order) считает стоимость сам, cost здесь только для показа.
import { ApiError, apiFetch } from "@/lib/api";

export type DeliveryZoneOption = {
  zone: string; // slug — уходит в PlaceOrderData.delivery_zone
  name: string;
  type: "courier" | "pickup";
  // Decimal → строка (для показа; сервер пересчитает сам). null — внешний
  // перевозчик (СДЭК): стоимость станет известна после оформления (DRF-2299).
  cost: string | null;
  free_delivery: boolean;
  // Зона внешнего перевозчика (СДЭК) и готов ли он считать доставку. Без
  // настроенного перевозчика способ СДЭК на чекауте не предлагается (DRF-2491).
  is_external?: boolean;
  carrier_available?: boolean;
};

export async function getDeliveryZones(
  cartTotal: number,
): Promise<DeliveryZoneOption[] | "error"> {
  try {
    const data = await apiFetch<{ zones: DeliveryZoneOption[] }>(
      `/api/delivery/zones?cart_total=${encodeURIComponent(cartTotal)}`,
      { method: "GET" },
    );
    return data.zones ?? [];
  } catch (e) {
    // Зоны — вспомогательные данные: их недоступность не должна ронять чекаут
    // (заказ без зоны создаётся как not_required — как и до этой фичи).
    // #574: но и молчать нельзя — раньше сбой был неотличим от пустого
    // справочника, и покупатель просто не видел выбора зоны без объяснения.
    if (e instanceof ApiError) return "error";
    throw e;
  }
}

// #569: слот доставки — дата + интервал. id уходит в PlaceOrderData.delivery_slot_id;
// сервер авторитетно перепроверит слот при оформлении.
export type DeliverySlotOption = {
  id: number;
  date: string; // ISO YYYY-MM-DD
  starts_at: string; // "10:00"
  ends_at: string; // "14:00"
};

export async function getDeliverySlots(
  zoneSlug?: string,
): Promise<DeliverySlotOption[] | "error"> {
  try {
    const qs = zoneSlug ? `?zone=${encodeURIComponent(zoneSlug)}` : "";
    const data = await apiFetch<{ slots: DeliverySlotOption[] }>(`/api/delivery/slots${qs}`, {
      method: "GET",
    });
    return data.slots ?? [];
  } catch (e) {
    // Пустой список = «слотов нет»: чекаут скрывает пикер и оформляет заказ
    // без слота (менеджер согласует время) — недоступность API не роняет заказ.
    // #574: сбой отдаём как "error" — «интервалов нет» и «не смогли загрузить»
    // это разные сообщения, второе предлагает повтор.
    if (e instanceof ApiError) return "error";
    throw e;
  }
}

// --- СДЭК (DRF-2491): справочники городов и пунктов и расчёт по серверной корзине ---

export type CdekMethod = "cdek_pvz" | "cdek_courier";

export type CdekCity = { code: number; name: string; full_name: string };

export type CdekPoint = {
  code: string;
  name: string;
  address: string;
  work_time: string;
  latitude: number | null;
  longitude: number | null;
};

export type CdekQuoteRequest = {
  zone: string;
  method: CdekMethod;
  city_code: number;
  city_name: string;
  pvz_code?: string;
  address?: string;
};

// Ответ расчёта. cost — строка Decimal, null при ручном расчёте (manual_required).
// Сумму доставки на сервер не отправляем: заказ находит расчёт по quote_id.
export type CdekQuote = {
  quote_id: string;
  status: "calculated" | "manual_required";
  cost: string | null;
  reason: string;
  period_min: number | null;
  period_max: number | null;
  address: string;
  city_name: string;
  free_delivery_promo_applies: boolean;
};

// Сбой обращения к СДЭК. unavailable — СДЭК выключен или не отвечает: чекаут
// переходит на ручной ввод адреса. busy — упёрлись в лимит запросов. invalid —
// ошибка ввода, field указывает поле формы.
export type CdekFailure = {
  kind: "unavailable" | "busy" | "invalid";
  message: string;
  field?: string;
};

export type CdekResult<T> = { ok: true; data: T } | ({ ok: false } & CdekFailure);

const CDEK_UNAVAILABLE = "Доставка СДЭК сейчас недоступна.";

export function cdekFailure(e: unknown): CdekFailure {
  if (e instanceof ApiError) {
    if (e.status === 429) {
      return { kind: "busy", message: "Слишком много запросов. Подождите минуту и повторите." };
    }
    // field "zone" — зону СДЭК выключили в админке: это недоступность, а не ошибка ввода.
    if (e.status === 400 && e.field !== "zone") {
      return { kind: "invalid", message: e.message, field: e.field };
    }
  }
  return { kind: "unavailable", message: CDEK_UNAVAILABLE };
}

async function cdekCall<T>(run: () => Promise<T>): Promise<CdekResult<T>> {
  try {
    return { ok: true, data: await run() };
  } catch (e) {
    return { ok: false, ...cdekFailure(e) };
  }
}

export function searchCdekCities(q: string, signal?: AbortSignal): Promise<CdekResult<CdekCity[]>> {
  return cdekCall(async () => {
    const data = await apiFetch<{ cities?: CdekCity[] }>(
      `/api/delivery/cdek/cities?q=${encodeURIComponent(q)}`,
      { method: "GET", signal },
    );
    return data.cities ?? [];
  });
}

export function getCdekPoints(cityCode: number): Promise<CdekResult<CdekPoint[]>> {
  return cdekCall(async () => {
    const data = await apiFetch<{ points?: CdekPoint[] }>(
      `/api/delivery/cdek/points?city_code=${encodeURIComponent(cityCode)}`,
      { method: "GET" },
    );
    return data.points ?? [];
  });
}

export function quoteCdekDelivery(body: CdekQuoteRequest): Promise<CdekResult<CdekQuote>> {
  return cdekCall(() =>
    apiFetch<CdekQuote>("/api/cart/delivery-quote", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

/** Срок доставки: «3 дн.», «2–4 дн.»; пусто, если СДЭК срок не дал. */
export function cdekPeriodText(min: number | null, max: number | null): string {
  if (!min && !max) return "";
  if (!min || !max || min === max) return `${max || min} дн.`;
  return `${min}–${max} дн.`;
}

/** Почему стоимость считает менеджер — текст для покупателя по reason расчёта. */
export function cdekManualText(reason: string): string {
  if (reason === "provider_unavailable" || reason === "provider_disabled") {
    return "СДЭК сейчас не отвечает — стоимость доставки рассчитает менеджер после оформления.";
  }
  return "Стоимость доставки этой посылки рассчитает менеджер после оформления.";
}
