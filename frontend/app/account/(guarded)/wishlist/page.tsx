"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Heart } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { ProductCard } from "@/components/product/ProductCard";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useWishlist } from "@/components/wishlist/WishlistProvider";
import type { Product } from "@/lib/types";
import { fetchWishlistProducts } from "@/lib/wishlist-products";

// Избранное покупателя. Доступ проверяет серверный гвард кабинета
// (app/account/(guarded)/layout.tsx) ещё до отдачи разметки — здесь остаётся
// только показать сохранённое.
//
// Карточки — обычные ProductCard: цена, наличие, «в корзину» и то же сердечко,
// что на витрине. Оно и снимает товар из избранного, поэтому отдельной кнопки
// удаления нет: две кнопки с одним смыслом на одной карточке путают.
export default function WishlistPage() {
  const { ids, loaded } = useWishlist();
  const [products, setProducts] = useState<Product[] | null>(null);
  const [failed, setFailed] = useState(false);

  // Список идентификаторов ведёт провайдер (он же обновляет его при клике по
  // сердечку), а карточки догружаем один раз — по мере появления новых id.
  // Строкой, а не Set: иначе effect перезапускался бы на каждый рендер.
  const idsKey = [...ids].sort((a, b) => a - b).join(",");

  useEffect(() => {
    // Пустое избранное грузить незачем — это видно по самому списку id.
    if (!loaded || !idsKey) return;
    let active = true;
    fetchWishlistProducts(idsKey.split(",").map(Number))
      .then((rows) => {
        if (active) setProducts(rows);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [idsKey, loaded]);

  // Что показываем: null — ещё грузим. Снятое сердечко убирает карточку сразу,
  // не дожидаясь перезагрузки списка.
  const visible = !loaded
    ? null
    : ids.size === 0
      ? []
      : (products?.filter((product) => ids.has(product.id)) ?? null);

  return (
    <AccountShell title="Избранное" mobileBackHref="/account/profile">
      <div className="space-y-4">
        {failed && (
          <ErrorState
            title="Не удалось загрузить избранное"
            description="Проверьте соединение и обновите страницу."
          />
        )}

        {!failed && (!loaded || visible === null) && (
          <LoadingState label="Загружаем избранное…" />
        )}

        {!failed && visible !== null && visible.length === 0 && (
          <EmptyState
            icon={<Heart className="h-10 w-10" aria-hidden />}
            title="В избранном пока пусто"
            description="Сохраняйте интересные товары, чтобы быстро вернуться к ним позже."
            action={
              <Link
                href="/catalog"
                className="inline-flex h-11 items-center rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink"
              >
                Перейти в каталог
              </Link>
            }
          />
        )}

        {visible !== null && visible.length > 0 && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
            {visible.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </div>
    </AccountShell>
  );
}
