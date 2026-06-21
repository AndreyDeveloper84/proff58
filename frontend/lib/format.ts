/** Цена в рублях без копеек, ru-локаль. */
export function formatPrice(value: number, currency: string = "RUB"): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}
