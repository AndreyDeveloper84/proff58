"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, Heart, LoaderCircle, Trash2 } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import {
  getMe,
  getWishlist,
  removeWishlistItem,
  type WishlistItem,
} from "@/lib/auth";

export default function WishlistPage() {
  const router = useRouter();
  const [items, setItems] = useState<WishlistItem[] | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getMe().then((user) => {
      if (!user) {
        router.push("/account/login");
        return;
      }
      getWishlist().then((data) => {
        if (!active) return;
        // #574: сбой загрузки не выдаём за «в избранном пока пусто».
        if (data === "error") setFailed(true);
        else setItems(data);
      });
    });
    return () => {
      active = false;
    };
  }, [router]);

  const removeItem = async (item: WishlistItem) => {
    if (removingId !== null || items === null) return;
    const previousItems = items;
    setError("");
    setRemovingId(item.product_id);
    setItems((current) =>
      current?.filter((entry) => entry.product_id !== item.product_id) ?? current,
    );
    try {
      await removeWishlistItem(item.product_id);
    } catch (caught) {
      setItems(previousItems);
      setError(caught instanceof Error ? caught.message : "Не удалось удалить товар.");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <AccountShell title="Избранное" mobileBackHref="/account/profile">
      <div className="space-y-4">
        {error && (
          <p
            role="alert"
            className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
          >
            {error}
          </p>
        )}

        {failed && (
          <ErrorState
            title="Не удалось загрузить избранное"
            description="Проверьте соединение и обновите страницу."
          />
        )}

        {!failed && items === null && <LoadingState label="Загружаем избранное…" />}

        {!failed && items !== null && items.length === 0 && (
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

        {items !== null && items.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <article
                key={item.product_id}
                className="group relative overflow-hidden rounded-lg border border-line bg-surface transition hover:-translate-y-0.5 hover:shadow-md"
              >
                <Link
                  href={`/product/${item.product_slug}`}
                  aria-label={`Открыть товар «${item.product_name}»`}
                  className="block"
                >
                  <div className="grid aspect-[4/3] place-items-center bg-photo">
                    <Image
                      src="/sample-tool.svg"
                      alt=""
                      width={160}
                      height={160}
                      className="h-32 w-32 object-contain transition group-hover:scale-105"
                    />
                  </div>
                </Link>
                <button
                  type="button"
                  onClick={() => void removeItem(item)}
                  disabled={removingId !== null}
                  aria-label={`Удалить «${item.product_name}» из избранного`}
                  className="absolute right-3 top-3 grid h-10 w-10 place-items-center rounded-full border border-line bg-surface text-danger shadow-sm transition hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
                >
                  {removingId === item.product_id ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="h-4 w-4" aria-hidden />
                  )}
                </button>
                <Link
                  href={`/product/${item.product_slug}`}
                  className="flex items-center gap-3 p-4"
                >
                  <p className="min-w-0 flex-1 text-sm font-semibold text-ink">
                    {item.product_name}
                  </p>
                  <ChevronRight
                    className="h-4 w-4 shrink-0 text-ink-3 transition group-hover:text-accent"
                    aria-hidden
                  />
                </Link>
              </article>
            ))}
          </div>
        )}
      </div>
    </AccountShell>
  );
}
