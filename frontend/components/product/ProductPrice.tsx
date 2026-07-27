import { cn } from "@/lib/utils";
import { formatPrice } from "@/lib/format";
import type { Product } from "@/lib/types";

// compact — масштаб карточки списка (text-lg); по умолчанию крупная цена для PDP/бай-бокса.
export function ProductPrice({
  price,
  compact = false,
  micro = false,
}: {
  price: Product["price"];
  compact?: boolean;
  micro?: boolean;
}) {
  if (price.final == null) {
    return <span className="font-display text-base text-ink-2">Цена по запросу</span>;
  }
  return (
    <div className="flex items-baseline gap-2">
      <span
        className={cn(
          "font-display font-bold text-ink",
          micro ? "text-[15px]" : compact ? "text-lg" : "text-2xl",
        )}
      >
        {formatPrice(price.final, price.currency)}
      </span>
      {price.old != null && price.old > price.final && (
        <span className={cn("text-ink-3 line-through", micro ? "text-[11px]" : "text-xs")}>
          {formatPrice(price.old, price.currency)}
        </span>
      )}
    </div>
  );
}
