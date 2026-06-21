"use client";

import { Bell, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { StockState } from "@/lib/types";

// CTA зависит от наличия и наличия цены — это разные сценарии покупки:
//   in    → В корзину (иконка, tooltip)
//   order → Под заказ
//   out   → Сообщить о поступлении
//   нет цены → Запросить цену
export function AddToCartButton({
  productId,
  stock = "in",
  hasPrice = true,
}: {
  productId: number;
  stock?: StockState;
  hasPrice?: boolean;
}) {
  if (!hasPrice) {
    return (
      <Button variant="outline" size="sm" data-event="request_price" data-product-id={productId}>
        Запросить цену
      </Button>
    );
  }
  if (stock === "out") {
    return (
      <Button variant="outline" size="sm" data-event="notify_restock" data-product-id={productId}>
        <Bell className="h-3.5 w-3.5" aria-hidden />
        Сообщить
      </Button>
    );
  }
  if (stock === "order") {
    return (
      <Button variant="outline" size="sm" data-event="preorder" data-product-id={productId}>
        Под заказ
      </Button>
    );
  }
  return (
    <Button
      size="icon"
      variant="accent"
      aria-label="В корзину"
      title="Добавить в корзину"
      data-event="add_to_cart_from_plp"
      data-product-id={productId}
    >
      <ShoppingCart className="h-4 w-4" aria-hidden />
    </Button>
  );
}
