"use client";

import { useCallback, useEffect, useState } from "react";
import { ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CartItemRow } from "@/components/cart/CartItemRow";
import { formatPrice } from "@/lib/format";
import type { Cart } from "@/lib/cart";
import { getCart, updateItem, removeItem } from "@/lib/cart";

export default function CartPage() {
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCart()
      .then(setCart)
      .catch(() => setError("Не удалось загрузить корзину"))
      .finally(() => setLoading(false));
  }, []);

  const handleUpdate = useCallback(async (itemId: number, qty: number) => {
    setMutating(true);
    try {
      const updated = await updateItem(itemId, qty);
      setCart(updated);
    } catch {
      setError("Не удалось обновить количество");
    } finally {
      setMutating(false);
    }
  }, []);

  const handleRemove = useCallback(async (itemId: number) => {
    setMutating(true);
    try {
      const updated = await removeItem(itemId);
      setCart(updated);
    } catch {
      setError("Не удалось удалить товар");
    } finally {
      setMutating(false);
    }
  }, []);

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </div>
      </main>
    );
  }

  if (error && !cart) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <p className="text-center text-danger">{error}</p>
      </main>
    );
  }

  const isEmpty = !cart || cart.lines.length === 0;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="mb-6 font-display text-3xl font-semibold uppercase tracking-wide text-ink">
        Корзина
      </h1>

      {error && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {isEmpty ? (
        <div className="flex flex-col items-center gap-4 rounded-lg border border-line bg-surface p-12 text-center">
          <ShoppingCart className="h-16 w-16 text-ink-3" strokeWidth={1} />
          <p className="text-lg text-ink-2">Корзина пуста</p>
          <p className="text-sm text-ink-3">
            Перейдите в каталог, чтобы добавить товары
          </p>
          <a href="/catalog/perforatory">
            <Button variant="accent">Перейти в каталог</Button>
          </a>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            {cart!.lines.map((line) => (
              <CartItemRow
                key={line.id}
                line={line}
                onUpdate={handleUpdate}
                onRemove={handleRemove}
                disabled={mutating}
              />
            ))}
          </div>

          {/* Итог */}
          <div className="mt-6 flex items-center justify-between rounded-lg border border-line bg-surface p-5">
            <span className="text-lg text-ink-2">Итого:</span>
            <span className="font-display text-2xl font-bold text-ink">
              {formatPrice(Number(cart!.total))}
            </span>
          </div>

          <div className="mt-4 flex justify-end">
            <a href="/checkout">
              <Button variant="accent" className="px-8 py-2.5 text-base">
                Оформить заказ
              </Button>
            </a>
          </div>
        </>
      )}
    </main>
  );
}
