"use client";

import { useState } from "react";
import { Clock, Heart } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Product } from "@/lib/types";
import { LOW_STOCK_THRESHOLD } from "@/lib/constants";
import { ProductImage } from "./ProductImage";
import { ProductPrice } from "./ProductPrice";
import { ProductSpecs } from "./ProductSpecs";
import { AddToCartButton } from "./AddToCartButton";

// Статус-лейбл карточки по макету: цветной текст сверху-слева. Комбинирует наличие и
// наличие цены (нет цены → «Цена уточняется» вне зависимости от остатка).
function statusInfo(product: Product): { label: string; cls: string; clock?: boolean } {
  if (product.price.final == null) return { label: "Цена уточняется", cls: "text-ink-3" };
  if (product.stock === "out") return { label: "Нет в наличии", cls: "text-danger" };
  if (product.stock === "order") return { label: "Под заказ", cls: "text-st-confirm", clock: true };
  if (
    product.stock === "in" &&
    product.stockQty != null &&
    product.stockQty > 0 &&
    product.stockQty <= LOW_STOCK_THRESHOLD
  )
    return { label: "Мало осталось", cls: "text-rating" };
  return { label: "В наличии", cls: "text-brand" };
}

function StatusLabel({ product }: { product: Product }) {
  const s = statusInfo(product);
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-semibold", s.cls)}>
      {s.clock ? (
        <Clock className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      )}
      {s.label}
    </span>
  );
}

export function ProductCard({
  product,
  view = "grid",
  showFavorite = false,
}: {
  product: Product;
  view?: "grid" | "list";
  // Избранное — Wave 2: по умолчанию скрыто, пока нет полного сценария.
  showFavorite?: boolean;
}) {
  const [fav, setFav] = useState(false);
  const href = `/product/${product.slug}`;
  const dimmed = product.stock === "out";
  const buyable = product.price.final != null && product.stock !== "out";

  const heart = (
    <button
      type="button"
      onClick={() => setFav((v) => !v)}
      aria-label="В избранное"
      aria-pressed={fav}
      data-event="favorite_toggle"
      data-product-id={product.id}
      className={cn(
        // #478: touch hit-area ≥44px на мобиле.
        "grid h-11 w-11 shrink-0 place-items-center rounded-full transition-colors sm:h-8 sm:w-8",
        fav ? "text-brand" : "text-ink-3 hover:text-brand",
      )}
    >
      <Heart className="h-4 w-4" fill={fav ? "currentColor" : "none"} />
    </button>
  );

  const media = (
    <a href={href} aria-label={product.name} className="relative block">
      {product.price.discountPct != null && (
        <span className="absolute left-2 top-2 z-10 rounded-md bg-danger px-1.5 py-0.5 text-[11px] font-bold text-white">
          −{product.price.discountPct}%
        </span>
      )}
      <ProductImage src={product.image} alt={product.name} />
    </a>
  );

  const priceCta = buyable ? (
    <div className="mt-auto flex items-end justify-between gap-2 pt-2">
      <ProductPrice price={product.price} compact />
      <AddToCartButton
        productId={product.id}
        stock={product.stock}
        hasPrice={product.price.final != null}
      />
    </div>
  ) : (
    <div className="mt-auto pt-2">
      <AddToCartButton
        productId={product.id}
        stock={product.stock}
        hasPrice={product.price.final != null}
        fullWidth
      />
    </div>
  );

  if (view === "list") {
    return (
      <article
        data-event="product_card_click"
        data-product-id={product.id}
        className={cn(
          "flex gap-4 rounded-lg border border-line bg-surface p-3 transition hover:shadow-sm",
          dimmed && "opacity-70",
        )}
      >
        <div className="w-40 shrink-0">{media}</div>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="mb-1 flex items-start justify-between gap-2">
            <StatusLabel product={product} />
            {heart}
          </div>
          <p className="text-xs text-ink-3">{product.brand}</p>
          <a href={href} className="mt-0.5 line-clamp-2 text-sm font-medium text-ink hover:text-accent">
            {product.name}
          </a>
          <div className="mt-1">
            <ProductSpecs specs={product.specs} />
          </div>
          {priceCta}
        </div>
      </article>
    );
  }

  return (
    <article
      data-event="product_card_click"
      data-product-id={product.id}
      className={cn(
        "group flex flex-col rounded-lg border border-line bg-surface p-3 transition duration-150 hover:-translate-y-0.5 hover:shadow-md motion-reduce:transform-none motion-reduce:transition-none",
        dimmed && "opacity-70",
      )}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <StatusLabel product={product} />
        {showFavorite ? heart : null}
      </div>
      <div className="mb-3">{media}</div>
      <p className="text-xs text-ink-3">{product.brand}</p>
      <a href={href} className="mt-0.5 line-clamp-2 text-sm font-medium text-ink hover:text-accent">
        {product.name}
      </a>
      <div className="mt-1">
        <ProductSpecs specs={product.specs} />
      </div>
      {priceCta}
    </article>
  );
}
