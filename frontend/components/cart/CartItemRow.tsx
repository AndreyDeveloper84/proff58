"use client";

import Link from "next/link";
import { Minus, Plus, Trash2 } from "lucide-react";
import { formatPrice } from "@/lib/format";
import type { CartLine } from "@/lib/types";

export function CartItemRow({
  line,
  onUpdate,
  onRemove,
  disabled,
}: {
  line: CartLine;
  onUpdate: (itemId: number, qty: number) => void;
  onRemove: (itemId: number) => void;
  disabled?: boolean;
}) {
  const price = line.price_final ? Number(line.price_final) : null;
  const total = line.line_total ? Number(line.line_total) : null;
  const basePrice = line.price_base ? Number(line.price_base) : null;
  const hasDiscount = basePrice != null && price != null && basePrice > price;

  return (
    <div className="flex items-center gap-4 rounded-lg border border-line bg-raised p-4">
      <div className="min-w-0 flex-1">
        <Link
          href={`/product/${line.slug}`}
          className="line-clamp-2 text-sm font-medium text-ink hover:text-accent"
        >
          {line.name}
        </Link>
        <div className="mt-1 flex items-baseline gap-2">
          {price != null ? (
            <>
              <span className="font-display text-sm font-semibold text-ink">
                {formatPrice(price)}
              </span>
              {hasDiscount && (
                <span className="text-xs text-ink-3 line-through">
                  {formatPrice(basePrice!)}
                </span>
              )}
            </>
          ) : (
            <span className="text-sm text-ink-3">Цена по запросу</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={disabled || line.quantity <= 1}
          onClick={() => onUpdate(line.id, line.quantity - 1)}
          className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink-2 transition hover:border-accent hover:text-accent disabled:opacity-40"
          aria-label="Уменьшить количество"
        >
          <Minus className="h-4 w-4" />
        </button>
        <span className="w-10 text-center font-display text-sm font-semibold text-ink">
          {line.quantity}
        </span>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onUpdate(line.id, line.quantity + 1)}
          className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink-2 transition hover:border-accent hover:text-accent disabled:opacity-40"
          aria-label="Увеличить количество"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      <div className="w-28 text-right">
        {total != null ? (
          <span className="font-display text-lg font-bold text-ink">
            {formatPrice(total)}
          </span>
        ) : (
          <span className="text-sm text-ink-3">&mdash;</span>
        )}
      </div>

      <button
        type="button"
        disabled={disabled}
        onClick={() => onRemove(line.id)}
        className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-3 transition hover:text-danger disabled:opacity-40"
        aria-label="Удалить из корзины"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}
