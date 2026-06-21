"use client";

import { useState } from "react";
import { Heart, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Product } from "@/lib/types";
import { ProductImage } from "./ProductImage";
import { ProductBadges } from "./ProductBadges";
import { ProductPrice } from "./ProductPrice";
import { ProductAvailability } from "./ProductAvailability";
import { ProductSpecs } from "./ProductSpecs";
import { AddToCartButton } from "./AddToCartButton";

export function ProductCard({
  product,
  view = "grid",
}: {
  product: Product;
  view?: "grid" | "list";
}) {
  const [fav, setFav] = useState(false);
  const href = `/product/${product.slug}`;
  const signature = product.energy ?? product.power ?? product.chuck;

  const media = (
    <div className="relative">
      <ProductBadges badges={product.badges} discountPct={product.price.discountPct} />
      <button
        type="button"
        onClick={() => setFav((v) => !v)}
        aria-label="В избранное"
        aria-pressed={fav}
        data-event="favorite_toggle"
        data-product-id={product.id}
        className={cn(
          "absolute right-2 top-2 z-10 grid h-8 w-8 place-items-center rounded-full bg-surface/70 backdrop-blur transition-colors",
          fav ? "text-brand" : "text-ink-3 hover:text-ink",
        )}
      >
        <Heart className="h-4 w-4" fill={fav ? "currentColor" : "none"} />
      </button>
      <ProductImage src={product.image} alt={product.name} />
      {signature && (
        <span className="absolute bottom-2 left-2 z-10 rounded-md bg-canvas/80 px-2 py-0.5 font-display text-sm font-semibold text-accent backdrop-blur">
          {signature}
        </span>
      )}
    </div>
  );

  const rating =
    product.rating != null ? (
      <span className="inline-flex items-center gap-1 text-xs text-ink-3">
        <Star className="h-3.5 w-3.5 text-rating" fill="currentColor" />
        <span className="text-ink-2">{product.rating.toFixed(1)}</span>
        {product.reviews != null && <span>({product.reviews})</span>}
      </span>
    ) : null;

  const title = (
    <a
      href={href}
      className="line-clamp-2 text-[15px] font-medium text-ink hover:text-accent"
    >
      {product.name}
    </a>
  );

  const isList = view === "list";

  return (
    <article
      data-event="product_card_click"
      data-product-id={product.id}
      className={cn(
        "group rounded-lg border border-line bg-surface p-3 transition duration-150 hover:border-accent motion-reduce:transition-none",
        isList
          ? "flex gap-4"
          : "flex flex-col gap-2.5 hover:-translate-y-0.5 hover:shadow-md motion-reduce:transform-none",
      )}
    >
      <a
        href={href}
        aria-label={product.name}
        className={isList ? "w-40 shrink-0 self-start" : undefined}
      >
        {media}
      </a>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-ink-3">{product.brand}</span>
          {rating}
        </div>
        {title}
        <ProductSpecs specs={product.specs} />
        <ProductAvailability stock={product.stock} />
        <div className="mt-auto flex items-center justify-between gap-2 pt-1">
          <ProductPrice price={product.price} />
          <AddToCartButton productId={product.id} />
        </div>
      </div>
    </article>
  );
}
