"use client";

import { ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AddToCartButton({ productId }: { productId: number }) {
  return (
    <Button
      size="icon"
      variant="accent"
      aria-label="В корзину"
      data-event="add_to_cart_from_plp"
      data-product-id={productId}
    >
      <ShoppingCart className="h-4 w-4" />
    </Button>
  );
}
