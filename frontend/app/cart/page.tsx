"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CartItemRow } from "@/components/cart/CartItemRow";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";
import { formatPrice } from "@/lib/format";

export default function CartPage() {
  const { cart, loading, total, update, remove } = useCart();
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Любая мутация возвращает свежий снимок (обновляет провайдер); блокируем строки на время.
  const run = useCallback(async (action: () => Promise<unknown>) => {
    setMutating(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось обновить корзину");
    } finally {
      setMutating(false);
    }
  }, []);

  const handleUpdate = useCallback(
    (itemId: number, qty: number) => run(() => update(itemId, qty)),
    [run, update],
  );
  const handleRemove = useCallback(
    (itemId: number) => run(() => remove(itemId)),
    [run, remove],
  );

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
        </div>
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
          <ShoppingCart className="h-16 w-16 text-ink-3" strokeWidth={1} aria-hidden />
          <p className="text-lg text-ink-2">Корзина пуста</p>
          <p className="text-sm text-ink-3">Перейдите в каталог, чтобы добавить товары</p>
          <Link href="/catalog">
            <Button variant="accent">Перейти в каталог</Button>
          </Link>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            {cart.lines.map((line) => (
              <CartItemRow
                key={line.id}
                line={line}
                onUpdate={handleUpdate}
                onRemove={handleRemove}
                disabled={mutating}
              />
            ))}
          </div>

          <div className="mt-6 flex items-center justify-between rounded-lg border border-line bg-surface p-5">
            <span className="text-lg text-ink-2">Итого:</span>
            <span className="font-display text-2xl font-bold text-ink">
              {formatPrice(total)}
            </span>
          </div>

          <div className="mt-4 flex justify-end">
            <Link href="/checkout">
              <Button variant="accent" className="px-8 py-2.5 text-base">
                Оформить заказ
              </Button>
            </Link>
          </div>
        </>
      )}
    </main>
  );
}
