import type { StockState } from "@/lib/types";
import { LOW_STOCK_THRESHOLD } from "@/lib/constants";

const MAP: Record<StockState, { label: string; text: string; dot: string }> = {
  in: { label: "В наличии", text: "text-ink-2", dot: "bg-brand" },
  order: { label: "Под заказ", text: "text-ink-3", dot: "bg-ink-3" },
  out: { label: "Нет в наличии", text: "text-danger", dot: "bg-danger" },
};

// «Мало осталось» — производное состояние (in-stock + малый остаток), а не отдельный
// StockState: бэк отдаёт только in/order/out. Показывается, когда 1С передаёт остаток
// (stockQty) ниже порога; до появления поля в API проп пуст и состояние «спит».
const LOW = { label: "Мало осталось", text: "text-rating", dot: "bg-rating" };

export function ProductAvailability({
  stock,
  stockQty,
}: {
  stock?: StockState;
  stockQty?: number;
}) {
  const low =
    stock === "in" && stockQty != null && stockQty > 0 && stockQty <= LOW_STOCK_THRESHOLD;
  const s = low
    ? LOW
    : stock
      ? MAP[stock]
      : { label: "Уточняйте наличие", text: "text-ink-3", dot: "bg-ink-3" };
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}
