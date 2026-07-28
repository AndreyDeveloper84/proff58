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
import { SITE } from "@/lib/site";

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

function StatusLabel({ product, compact = false }: { product: Product; compact?: boolean }) {
  const s = statusInfo(product);
  return (
    <span
      className={cn(
        // whitespace-nowrap: рядом может стоять бейдж «Хит», и «В наличии»
        // ломалось на две строки, задирая высоту шапки карточки.
        "inline-flex shrink-0 items-center gap-1 whitespace-nowrap font-semibold",
        compact ? "text-[10px]" : "text-xs",
        s.cls,
      )}
    >
      {s.clock ? (
        <Clock className={compact ? "h-3 w-3" : "h-3.5 w-3.5"} aria-hidden />
      ) : (
        <span
          className={cn("rounded-full bg-current", compact ? "h-1 w-1" : "h-1.5 w-1.5")}
          aria-hidden
        />
      )}
      {s.label}
    </span>
  );
}

export function ProductCard({
  product,
  view = "grid",
  showFavorite = true,
  variant = "default",
  maxHref = SITE.support.max.href,
}: {
  product: Product;
  view?: "grid" | "list";
  // Избранное — Wave 2: сердце присутствует в шаблоне по референсу, но это ещё не
  // завершённая функция (локальное визуальное состояние, без бэкенда/персистентности).
  showFavorite?: boolean;
  variant?: "default" | "home";
  maxHref?: string;
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
        productSlug={product.slug}
        stock={product.stock}
        hasPrice={product.price.final != null}
      />
    </div>
  ) : (
    <div className="mt-auto pt-2">
      <AddToCartButton
        productId={product.id}
        productSlug={product.slug}
        stock={product.stock}
        hasPrice={product.price.final != null}
        fullWidth
      />
    </div>
  );

  if (variant === "home") {
    return (
      <article
        data-event="product_card_click"
        data-product-id={product.id}
        className={cn(
          "relative flex h-[212px] flex-col overflow-hidden rounded-sm border border-line bg-surface",
          dimmed && "opacity-70",
        )}
      >
        <div className="absolute left-2 top-2 z-10 flex gap-1">
          {product.price.discountPct != null && (
            <span className="rounded-full bg-danger px-2 py-0.5 text-[10px] font-bold text-white">
              −{product.price.discountPct}%
            </span>
          )}
          {product.badges.includes("hit") && (
            <span className="rounded-full bg-[#ff8700] px-2 py-0.5 text-[10px] font-bold text-white">
              Хит
            </span>
          )}
        </div>

        {showFavorite && (
          <div className="absolute right-1 top-0.5 z-10 scale-75">{heart}</div>
        )}

        <div className="flex min-h-0 flex-1 flex-col px-2 pt-1.5">
          <a href={href} aria-label={product.name} className="block">
            <ProductImage
              src={product.image}
              alt={product.name}
              sizes="220px"
              className="h-[88px] w-full aspect-auto rounded-none bg-surface"
            />
          </a>
          <a
            href={href}
            className="line-clamp-2 min-h-[29px] text-[11px] font-semibold leading-[1.25] text-ink hover:text-accent"
          >
            {product.brand ? `${product.brand} ` : ""}
            {product.name}
          </a>
          <div className="mt-0.5 line-clamp-1 text-[10px] leading-tight text-ink-2">
            {product.specs?.slice(0, 3).map((s) => s.value).join(" · ")}
          </div>
          <div className="mt-1 flex items-end justify-between gap-2">
            <div>
              <StatusLabel product={product} compact />
              <ProductPrice price={product.price} micro />
            </div>
            <AddToCartButton
              productId={product.id}
              productSlug={product.slug}
              stock={product.stock}
              hasPrice={product.price.final != null}
              compact
            />
          </div>
        </div>

        <a
          href={maxHref}
          target="_blank"
          rel="noopener noreferrer"
          className="flex h-6 shrink-0 items-center justify-center border-t border-line text-[10px] font-medium text-[#6156f5] hover:bg-[#f7f6ff]"
          aria-label={`Консультация в MAX по товару ${product.name}`}
        >
          Консультация в MAX
        </a>
      </article>
    );
  }

  // Бейдж «Хит» — из product.badges, куда его кладёт adapters по признаку
  // is_hit backend (рейтинг продаж). Ручных пометок здесь нет и быть не должно.
  const hitBadge = product.badges.includes("hit") ? (
    <span className="shrink-0 rounded-full bg-[#ff8700] px-2 py-0.5 text-[10px] font-bold text-white">
      Хит
    </span>
  ) : null;

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
            <div className="flex min-w-0 items-center gap-1.5">
              <StatusLabel product={product} />
              {hitBadge}
            </div>
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
        <div className="flex min-w-0 items-center gap-1.5">
          <StatusLabel product={product} />
          {hitBadge}
        </div>
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
