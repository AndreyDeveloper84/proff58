import { formatPrice } from "@/lib/format";
import type { Product } from "@/lib/types";

export function ProductPrice({ price }: { price: Product["price"] }) {
  if (price.final == null) {
    return (
      <span className="font-display text-base text-ink-2">Цена по запросу</span>
    );
  }
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-display text-xl font-semibold text-ink">
        {formatPrice(price.final, price.currency)}
      </span>
      {price.old != null && price.old > price.final && (
        <span className="text-xs text-ink-3 line-through">
          {formatPrice(price.old, price.currency)}
        </span>
      )}
    </div>
  );
}
