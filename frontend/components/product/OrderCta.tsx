import { Bell, FileText, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { StockState } from "@/lib/types";

// CTA карточки товара (PDP, #242) — ЗАЯВОЧНЫЙ, не настоящая корзина (её подключим в #243).
// Тексты не обещают корзину:
//   нет цены        → «Запросить цену»
//   нет в наличии   → «Уточнить поступление»
//   цена + наличие  → «Заказать»
// data-event — для аналитики (как в AddToCartButton); реальный add-to-cart — отдельная задача.
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
  return (
    <Button variant="accent" data-event="order_request" data-product-id={productId}>
      <ShoppingCart className="h-4 w-4" aria-hidden />
      Заказать
    </Button>
  );
}
