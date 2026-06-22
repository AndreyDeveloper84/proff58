import type { StockState } from "@/lib/types";

const MAP: Record<StockState, { label: string; text: string; dot: string }> = {
  in: { label: "В наличии", text: "text-ink-2", dot: "bg-brand" },
  order: { label: "Под заказ", text: "text-ink-3", dot: "bg-ink-3" },
  out: { label: "Нет в наличии", text: "text-danger", dot: "bg-danger" },
};

export function ProductAvailability({ stock }: { stock?: StockState }) {
  const s = stock
    ? MAP[stock]
    : { label: "Уточняйте наличие", text: "text-ink-3", dot: "bg-ink-3" };
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}
