"use client";

import { useEffect, useState } from "react";
import type { Product } from "@/lib/types";
import { ProductPrice } from "./ProductPrice";
import { OrderCta } from "./OrderCta";

// Липкая панель покупки: показывается, когда основной блок (#buybox-anchor) ушёл из
// вьюпорта при скролле. На мобиле фиксирована снизу. Переиспользует ProductPrice/OrderCta.
export function StickyBuyBar({
  product,
}: {
  product: Pick<Product, "id" | "name" | "price" | "stock">;
}) {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const anchor = document.getElementById("buybox-anchor");
    if (!anchor) return;
    const obs = new IntersectionObserver(
      ([entry]) => setShown(!entry.isIntersecting),
      { threshold: 0 },
    );
    obs.observe(anchor);
    return () => obs.disconnect();
  }, []);

  if (!shown) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm text-ink-2">{product.name}</p>
          <ProductPrice price={product.price} />
        </div>
        <OrderCta
          productId={product.id}
          stock={product.stock}
          hasPrice={product.price.final != null}
        />
      </div>
    </div>
  );
}
