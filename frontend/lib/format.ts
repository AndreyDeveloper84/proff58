/** Цена в рублях без копеек, ru-локаль. */
export function formatPrice(value: number, currency: string = "RUB"): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

/** Число для чипов/подписей по-русски: десятичная запятая (10.5 → «10,5»). */
export function formatRu(n: number): string {
  return String(n).replace(".", ",");
}

/**
 * Русская множественная форма по числу: pluralize(1,"товар","товара","товаров") → «товар»,
 * (2)→«товара», (5)→«товаров». one — 1/21/31…, few — 2–4/22–24…, many — 0/5–20/…
 */
export function pluralize(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(n) % 100;
  const tail = abs % 10;
  if (abs > 10 && abs < 20) return many;
  if (tail > 1 && tail < 5) return few;
  if (tail === 1) return one;
  return many;
}

// #574: единые форматы даты. Раньше каждая страница объявляла свой хелпер, и один
// и тот же отзыв в кабинете и на карточке товара датировался по-разному.

/** Дата → «21.07.2026». Для списков, карточек, дат отзыва. */
export function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** Дата и время → «21.07.2026, 14:30». Для резерва, счетов, «оформлен …». */
export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** День слота доставки (#569) → «вт, 21 июля». Подпись группы в пикере. */
export function formatSlotDay(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString("ru-RU", {
    weekday: "short",
    day: "numeric",
    month: "long",
  });
}

/** Слот доставки (#569): снимок из заказа → «21.07.2026, 10:00–14:00». */
export function formatDeliverySlot(slot: {
  date: string;
  starts_at: string;
  ends_at: string;
}): string {
  const date = new Date(`${slot.date}T00:00:00`).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  return `${date}, ${slot.starts_at}–${slot.ends_at}`;
}

/** slug/токен → человекочитаемая подпись: «cordless-drill» → «Cordless drill». */
export function humanizeToken(token: string): string {
  const s = token.replace(/[-_]/g, " ").trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/**
 * Подпись чипа диапазона с единицами по-русски: «Диаметр: от 10,5 до 20 мм» (§9.2).
 * Пустые границы опускаются; unit добавляется в конце, если задан.
 */
export function rangeChipLabel(
  label: string,
  min: number | undefined,
  max: number | undefined,
  unit?: string,
): string {
  const parts: string[] = [];
  if (min != null) parts.push(`от ${formatRu(min)}`);
  if (max != null) parts.push(`до ${formatRu(max)}`);
  const u = unit ? ` ${unit}` : "";
  return `${label}: ${parts.join(" ")}${u}`.trim();
}
