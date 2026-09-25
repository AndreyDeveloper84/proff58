"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Heart, Info } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { useAuthState } from "@/components/auth/AuthStateProvider";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { ProductCard } from "@/components/product/ProductCard";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useWishlist } from "@/components/wishlist/WishlistProvider";
import { loginHref } from "@/lib/auth-state";
import type { Product } from "@/lib/types";
import { cn } from "@/lib/utils";
import { fetchWishlistProducts } from "@/lib/wishlist-products";

// Избранное покупателя — обычная страница витрины, рядом со сравнением, а не
// раздел кабинета: сохранять товары можно и без аккаунта, а страница за гвардом
// кабинета гостю недоступна в принципе.
//
// Карточки — обычные ProductCard: цена, наличие, «в корзину» и то же сердечко,
// что на витрине. Оно и снимает товар из избранного, поэтому отдельной кнопки
// удаления нет: две кнопки с одним смыслом на одной карточке путают.
export default function WishlistPage() {
  const { ids, loaded, isGuest } = useWishlist();
  // Вошедшему та же страница показывается в обвязке кабинета. «Избранное» стоит
  // в меню кабинета, и переход по нему выбрасывал человека на витрину — со
  // стороны это выглядело так, будто кабинет закрылся сам. Гостю кабинет
  // показывать нечего: у него нет ни заказов, ни счетов.
  const inAccount = useAuthState() !== "anonymous";
  const [products, setProducts] = useState<Product[] | null>(null);
  const [failed, setFailed] = useState(false);

  // Список идентификаторов ведёт провайдер (он же обновляет его при клике по
  // сердечку), а карточки догружаем по мере появления новых id. Строкой, а не
  // Set: иначе effect перезапускался бы на каждый рендер.
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

  const content = (
    <div className="space-y-4">
      {/* Гостю честно говорим, где лежит его список: иначе «избранное
          пропало» на другом устройстве выглядит как потеря данных. */}
      {isGuest && ids.size > 0 && (
        <p className="flex items-start gap-2 rounded-lg border border-line bg-raised/60 px-4 py-3 text-sm text-ink-2">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" aria-hidden />
          <span>
            Избранное хранится в этом браузере.{" "}
            <Link
              href={loginHref("/wishlist")}
              className="font-medium text-accent hover:underline"
            >
              Войдите
            </Link>{" "}
            — и оно будет доступно на любом устройстве.
          </span>
        </p>
      )}

      {failed && (
        <ErrorState
          title="Не удалось загрузить избранное"
          description="Проверьте соединение и обновите страницу."
        />
      )}

      {!failed && (!loaded || visible === null) && <LoadingState label="Загружаем избранное…" />}

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
        <div
          className={cn(
            "grid grid-cols-2 gap-3 sm:grid-cols-3",
            // В кабинете колонку сужает боковое меню — пятый столбец там
            // сплющивал карточки до нечитаемой ширины.
            inAccount ? "lg:grid-cols-3 xl:grid-cols-4" : "lg:grid-cols-4 xl:grid-cols-5",
          )}
        >
          {visible.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      )}
    </div>
  );

  if (inAccount) return <AccountShell title="Избранное">{content}</AccountShell>;

  return (
    <main className="mx-auto w-full max-w-[1680px] px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-7">
      <nav
        aria-label="Хлебные крошки"
        className="mb-3 hidden items-center gap-2 text-xs text-ink-3 sm:flex"
      >
        <Link href="/" className="hover:text-accent">
          Главная
        </Link>
        <span aria-hidden>›</span>
        <span>Избранное</span>
      </nav>

      <h1 className="font-display text-2xl font-semibold text-ink lg:text-[30px]">Избранное</h1>

      <div className="mt-4">{content}</div>

      <MobileBottomNav active="account" />
    </main>
  );
}
