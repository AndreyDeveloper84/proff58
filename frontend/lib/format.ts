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
