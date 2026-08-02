"use client";

import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Product } from "@/lib/types";
import { ProductPrice } from "./ProductPrice";
import { OrderCta } from "./OrderCta";

/** Прокрутить к основному блоку покупки — там единственный CTA подписки. */
function scrollToBuybox() {
  const anchor = document.getElementById("buybox-anchor");
  anchor?.scrollIntoView?.({ block: "center", behavior: "smooth" });
}

// Липкая панель покупки: показывается, когда основной блок (#buybox-anchor) ушёл из
// вьюпорта при скролле. На мобиле фиксирована снизу. Переиспользует ProductPrice/OrderCta.
// Примечание: счётчик количества здесь — отдельный экземпляр и не синхронизирован
// с основным блоком (осознанно, для MVP).
//
// #574: для товара «нет в наличии» здесь НЕ рендерится вторая подписка на
// поступление. Два экземпляра AvailabilitySubscribeCta независимо опрашивали
// getMe()/статус подписки и расходились в состоянии (подписался в одном — второй
// об этом не знал), а карточка с MAX-привязкой ещё и раздувала фиксированную
// панель. Вместо этого — кнопка-якорь к основному блоку с единственным CTA.
export function StickyBuyBar({
  product,
}: {
  product: Pick<Product, "id" | "slug" | "name" | "price" | "stock">;
}) {
  const [passedBuybox, setPassedBuybox] = useState(false);
  const [atFooter, setAtFooter] = useState(false);

  useEffect(() => {
    const anchor = document.getElementById("buybox-anchor");
    if (!anchor) return;
    const obs = new IntersectionObserver(([entry]) => setPassedBuybox(!entry.isIntersecting), {
      threshold: 0,
    });
    obs.observe(anchor);
    return () => obs.disconnect();
  }, []);

  // У подвала панель убирается: она фиксирована снизу и накрывала последнюю
  // строку контактов и копирайт — телефон и режим работы дочитать было нельзя.
  useEffect(() => {
    const footer = document.querySelector("footer");
    if (!footer) return;
    const obs = new IntersectionObserver(([entry]) => setAtFooter(entry.isIntersecting), {
      threshold: 0,
    });
    obs.observe(footer);
    return () => obs.disconnect();
  }, []);

  if (!passedBuybox || atFooter) return null;

  return (
    <div
      role="region"
      aria-label="Быстрая покупка"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80"
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-ink-2">{product.name}</p>
          <ProductPrice price={product.price} />
        </div>
        <div className="shrink-0">
          {product.stock === "out" ? (
            <Button variant="outline" onClick={scrollToBuybox}>
              <BellRing className="h-4 w-4" aria-hidden />
              Сообщить о поступлении
            </Button>
          ) : (
            <OrderCta
              productId={product.id}
              productSlug={product.slug}
              stock={product.stock}
              hasPrice={product.price.final != null}
            />
          )}
        </div>
      </div>
    </div>
  );
}
