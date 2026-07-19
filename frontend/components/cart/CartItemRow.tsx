"use client";

import Image from "next/image";
import Link from "next/link";
import { Minus, Plus, X } from "lucide-react";
import { formatPrice } from "@/lib/format";
import type { CartLine } from "@/lib/types";

export function CartItemRow({
  line,
  selected,
  onSelect,
  onUpdate,
  onRemove,
  disabled,
}: {
  line: CartLine;
  selected: boolean;
  onSelect: (itemId: number, selected: boolean) => void;
  onUpdate: (itemId: number, qty: number) => void;
  onRemove: (itemId: number) => void;
  disabled?: boolean;
}) {
  const price = line.price_final ? Number(line.price_final) : null;
  const total = line.line_total ? Number(line.line_total) : null;
  const basePrice = line.price_base ? Number(line.price_base) : null;
  const hasDiscount = basePrice != null && price != null && basePrice > price;

  return (
    <article className="grid grid-cols-[20px_72px_minmax(0,1fr)_32px] items-center gap-x-3 gap-y-2 border-b border-line bg-surface px-3 py-4 last:border-b-0 sm:px-4 lg:grid-cols-[20px_112px_minmax(0,1fr)_110px_116px_120px_32px] lg:gap-x-4">
      <input
        type="checkbox"
        checked={selected}
        disabled={disabled}
        onChange={(event) => onSelect(line.id, event.target.checked)}
        aria-label={`Выбрать ${line.name}`}
        className="h-4 w-4 rounded border-line accent-accent"
      />

      <Link
        href={`/product/${line.slug}`}
        className="grid h-[72px] place-items-center rounded-md bg-photo lg:h-24"
        aria-label={`Открыть товар «${line.name}»`}
      >
        <Image
          src="/sample-tool.svg"
          alt=""
          width={96}
          height={96}
          className="h-16 w-16 object-contain lg:h-20 lg:w-20"
        />
      </Link>

      <div className="min-w-0 self-center">
        <Link
          href={`/product/${line.slug}`}
          className="line-clamp-2 text-sm font-semibold text-ink transition hover:text-accent"
        >
          {line.name}
        </Link>
        <p className="mt-1 text-[11px] text-ink-3">Код товара: {line.product_id}</p>
        <p className="mt-1 text-[11px] font-medium text-accent">В корзине</p>
        <div className="mt-2 flex items-baseline gap-2 lg:hidden">
          {total != null ? (
            <span className="text-sm font-bold text-ink">{formatPrice(total)}</span>
          ) : (
            <span className="text-xs text-ink-3">Цена по запросу</span>
          )}
          {hasDiscount && (
            <span className="text-[11px] text-ink-3 line-through">
              {formatPrice(basePrice! * line.quantity)}
            </span>
          )}
        </div>
      </div>

      <div className="hidden text-right lg:block">
        {price != null ? (
          <>
            <p className="text-sm font-semibold text-ink">{formatPrice(price)}</p>
            {hasDiscount && (
              <p className="mt-1 text-[11px] text-ink-3 line-through">
                {formatPrice(basePrice!)}
              </p>
            )}
          </>
        ) : (
          <span className="text-xs text-ink-3">По запросу</span>
        )}
      </div>

      <div className="col-span-2 col-start-3 flex items-center justify-start lg:col-span-1 lg:col-start-auto lg:justify-center">
        <div className="flex h-9 items-center rounded-md border border-line bg-surface">
          <button
            type="button"
            disabled={disabled || line.quantity <= 1}
            onClick={() => onUpdate(line.id, line.quantity - 1)}
            className="grid h-9 w-9 place-items-center text-ink-2 transition hover:text-accent disabled:opacity-35"
            aria-label="Уменьшить количество"
          >
            <Minus className="h-3.5 w-3.5" aria-hidden />
          </button>
          <span className="w-8 text-center text-sm font-semibold text-ink">
            {line.quantity}
          </span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onUpdate(line.id, line.quantity + 1)}
            className="grid h-9 w-9 place-items-center text-ink-2 transition hover:text-accent disabled:opacity-35"
            aria-label="Увеличить количество"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>

      <div className="hidden text-right lg:block">
        {total != null ? (
          <span className="text-base font-bold text-ink">{formatPrice(total)}</span>
        ) : (
          <span className="text-sm text-ink-3">&mdash;</span>
        )}
      </div>

      <button
        type="button"
        disabled={disabled}
        onClick={() => onRemove(line.id)}
        className="col-start-4 row-start-1 grid h-8 w-8 shrink-0 place-items-center self-start rounded-md text-ink-3 transition hover:bg-raised hover:text-danger disabled:opacity-40 lg:col-start-auto lg:row-start-auto lg:self-center"
        aria-label={`Удалить ${line.name} из корзины`}
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
    </article>
  );
}
