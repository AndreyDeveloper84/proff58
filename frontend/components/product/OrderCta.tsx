"use client";

import { useEffect, useRef, useState } from "react";
import { Bell, Check, FileText, Loader2, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";
import type { StockState } from "@/lib/types";

// CTA карточки товара (PDP). Для товара в наличии с ценой — РЕАЛЬНОЕ добавление в корзину (#246);
// прочие сценарии — заявочные (аналитика), реальной корзины для них нет:
//   нет цены        → «Запросить цену»
//   нет в наличии   → «Уточнить поступление»
//   цена + наличие  → «В корзину»
export function OrderCta({
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
      <Button variant="accent" data-event="request_price" data-product-id={productId}>
        <FileText className="h-4 w-4" aria-hidden />
        Запросить цену
      </Button>
    );
  }
  if (stock === "out") {
    return (
      <Button variant="outline" data-event="notify_restock" data-product-id={productId}>
        <Bell className="h-4 w-4" aria-hidden />
        Уточнить поступление
      </Button>
    );
  }
  return <AddToCartCta productId={productId} />;
}

type Phase = "idle" | "loading" | "added" | "error";

function AddToCartCta({ productId }: { productId: number }) {
  const { add } = useCart();
  const [phase, setPhase] = useState<Phase>("idle");
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
      if (!(err instanceof ApiError)) console.error(err);
    }
  };

  return (
    <Button
      variant="accent"
      disabled={phase === "loading"}
      onClick={handleClick}
      data-event="add_to_cart_from_pdp"
      data-product-id={productId}
    >
      {phase === "loading" ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : phase === "added" ? (
        <Check className="h-4 w-4" aria-hidden />
      ) : (
        <ShoppingCart className="h-4 w-4" aria-hidden />
      )}
      {phase === "added"
        ? "Добавлено"
        : phase === "error"
          ? "Ошибка, повторить"
          : "В корзину"}
    </Button>
  );
}
