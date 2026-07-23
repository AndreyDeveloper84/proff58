"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, Check, FileText, Loader2, ShoppingCart } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";
import type { StockState } from "@/lib/types";
import { cn } from "@/lib/utils";

// CTA зависит от наличия и наличия цены — это разные сценарии покупки:
//   in    → В корзину (реальное добавление через useCart)
//   order → Под заказ (заявочный, аналитика)
//   out   → Сообщить о поступлении → ведём на PDP, там живёт подписка
//   нет цены → Запросить цену → ведём на PDP, там модалка заявки
//
// #574: заявочные кнопки раньше рендерились без onClick и вообще ничего не
// делали (глобального обработчика data-event нет, lib/analytics.track — no-op).
// Настоящее действие для обоих сценариев есть только на карточке товара, поэтому
// это ссылки на PDP, а не мёртвые кнопки. Тексты выровнены с PDP.
export function AddToCartButton({
  productId,
  productSlug,
  stock = "in",
  hasPrice = true,
  fullWidth = false,
}: {
  productId: number;
  productSlug: string;
  stock?: StockState;
  hasPrice?: boolean;
  // fullWidth — растянуть заявочные кнопки (нет в наличии / нет цены) на всю ширину карточки.
  fullWidth?: boolean;
}) {
  const wide = fullWidth ? "w-full" : "";
  const href = `/product/${productSlug}`;
  if (!hasPrice) {
    return (
      <Link
        href={href}
        className={cn(buttonVariants({ variant: "outline" }), wide)}
        data-event="request_price"
        data-product-id={productId}
      >
        <FileText className="h-4 w-4" aria-hidden />
        Запросить цену
      </Link>
    );
  }
  if (stock === "out") {
    return (
      <Link
        href={href}
        className={cn(buttonVariants({ variant: "outline" }), wide)}
        data-event="notify_restock"
        data-product-id={productId}
      >
        <Bell className="h-4 w-4" aria-hidden />
        Сообщить о поступлении
      </Link>
    );
  }
  // in / order / низкий остаток → добавление в корзину (под заказ — предзаказ в корзину).
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
