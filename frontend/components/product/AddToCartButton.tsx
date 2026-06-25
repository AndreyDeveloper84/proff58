"use client";

import { useEffect, useRef, useState } from "react";
import { Bell, Check, Loader2, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";
import type { StockState } from "@/lib/types";

// CTA зависит от наличия и наличия цены — это разные сценарии покупки:
//   in    → В корзину (реальное добавление через useCart)
//   order → Под заказ (заявочный, аналитика)
//   out   → Сообщить о поступлении (заявочный)
//   нет цены → Запросить цену (заявочный)
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
  return <AddInStockButton productId={productId} />;
}

type Phase = "idle" | "loading" | "added" | "error";

// Реальное добавление в корзину для товара в наличии с ценой.
function AddInStockButton({ productId }: { productId: number }) {
  const { add } = useCart();
  const [phase, setPhase] = useState<Phase>("idle");
  // Очищаем таймер «Добавлено»/«ошибка» при размонтировании, чтобы не дёргать состояние.
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const handleClick = async () => {
    if (phase === "loading") return;
    setPhase("loading");
    try {
      await add(productId, 1);
      setPhase("added");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setPhase("idle"), 1800);
    } catch (err) {
      setPhase("error");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setPhase("idle"), 2500);
      // Тихо для UI: показываем «ошибку» на кнопке; детали — в консоль для отладки.
      if (!(err instanceof ApiError)) console.error(err);
    }
  };

  const label =
    phase === "added"
      ? "Добавлено в корзину"
      : phase === "error"
        ? "Не удалось добавить"
        : "Добавить в корзину";

  return (
    <Button
      size="icon"
      variant="accent"
      aria-label={label}
      title={label}
      disabled={phase === "loading"}
      onClick={handleClick}
      data-event="add_to_cart_from_plp"
      data-product-id={productId}
    >
      {phase === "loading" ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : phase === "added" ? (
        <Check className="h-4 w-4" aria-hidden />
      ) : (
        <ShoppingCart className="h-4 w-4" aria-hidden />
      )}
    </Button>
  );
}
