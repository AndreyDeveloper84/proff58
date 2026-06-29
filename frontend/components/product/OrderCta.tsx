"use client";

import { useEffect, useRef, useState } from "react";
import { Bell, Check, FileText, Loader2, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";
import type { StockState } from "@/lib/types";
import { QuantityStepper } from "./QuantityStepper";
import { InquiryDialog } from "./InquiryDialog";

// CTA карточки товара (PDP). Сценарии:
//   нет цены        → «Запросить цену»     → модалка заявки (price_request)
//   нет в наличии   → «Уточнить поступление» → модалка заявки (restock_notify)
//   in / order      → выбор количества + добавление в корзину (под заказ — тот же поток)
export function OrderCta({
  productId,
  stock = "in",
  hasPrice = true,
}: {
  productId: number;
  stock?: StockState;
  hasPrice?: boolean;
}) {
  const [dialog, setDialog] = useState<null | "price_request" | "restock_notify">(null);

  if (!hasPrice) {
    return (
      <>
        <Button
          variant="accent"
          onClick={() => setDialog("price_request")}
          data-event="request_price"
          data-product-id={productId}
        >
          <FileText className="h-4 w-4" aria-hidden />
          Запросить цену
        </Button>
        {dialog && (
          <InquiryDialog
            open
            onClose={() => setDialog(null)}
            productId={productId}
            kind={dialog}
            title={dialog === "price_request" ? "Запросить цену" : "Уточнить поступление"}
          />
        )}
      </>
    );
  }

  if (stock === "out") {
    return (
      <>
        <Button
          variant="outline"
          onClick={() => setDialog("restock_notify")}
          data-event="notify_restock"
          data-product-id={productId}
        >
          <Bell className="h-4 w-4" aria-hidden />
          Уточнить поступление
        </Button>
        {dialog && (
          <InquiryDialog
            open
            onClose={() => setDialog(null)}
            productId={productId}
            kind={dialog}
            title={dialog === "price_request" ? "Запросить цену" : "Уточнить поступление"}
          />
        )}
      </>
    );
  }

  return <AddToCartCta productId={productId} isOrder={stock === "order"} />;
}

type Phase = "idle" | "loading" | "added" | "error";

function AddToCartCta({ productId, isOrder }: { productId: number; isOrder: boolean }) {
  const { add } = useCart();
  const [qty, setQty] = useState(1);
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
      await add(productId, qty);
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

  const label = isOrder ? "Под заказ" : "В корзину";

  return (
    <div className="flex items-center gap-3">
      <QuantityStepper value={qty} min={1} onChange={setQty} disabled={phase === "loading"} />
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
        {phase === "added" ? "Добавлено" : phase === "error" ? "Ошибка, повторить" : label}
      </Button>
    </div>
  );
}
