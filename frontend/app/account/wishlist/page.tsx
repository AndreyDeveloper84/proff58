"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, Heart } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { getMe, getWishlist, type WishlistItem } from "@/lib/auth";

export default function WishlistPage() {
  const router = useRouter();
  const [items, setItems] = useState<WishlistItem[] | null>(null);

  useEffect(() => {
    let active = true;
    getMe().then((user) => {
      if (!user) {
        router.push("/account/login");
        return;
      }
      getWishlist().then((data) => {
        if (active) setItems(data);
      });
    });
    return () => {
      active = false;
    };
  }, [router]);

  return (
    <AccountShell title="Избранное" mobileBackHref="/account/profile">
      {items === null && (
        <div
          className="h-56 animate-pulse rounded-lg border border-line bg-surface"
          aria-label="Загрузка избранного"
        />
      )}

      {items !== null && items.length === 0 && (
        <section className="rounded-lg border border-line bg-surface px-5 py-12 text-center">
          <Heart className="mx-auto h-10 w-10 text-ink-3" aria-hidden />
          <h2 className="mt-3 text-base font-semibold text-ink">В избранном пока пусто</h2>
          <p className="mx-auto mt-1 max-w-sm text-sm text-ink-3">
            Сохраняйте интересные товары, чтобы быстро вернуться к ним позже.
          </p>
          <Link
            href="/catalog"
            className="mt-5 inline-flex h-11 items-center rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink"
          >
            Перейти в каталог
          </Link>
        </section>
      )}

      {items !== null && items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => (
            <Link
              key={item.product_id}
              href={`/product/${item.product_slug}`}
              className="group overflow-hidden rounded-lg border border-line bg-surface transition hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="relative grid aspect-[4/3] place-items-center bg-photo">
                <Image
                  src="/sample-tool.svg"
                  alt=""
                  width={160}
                  height={160}
                  className="h-32 w-32 object-contain transition group-hover:scale-105"
                />
                <span className="absolute right-3 top-3 grid h-9 w-9 place-items-center rounded-full bg-surface text-accent shadow-sm">
                  <Heart className="h-4 w-4 fill-current" aria-hidden />
                </span>
              </div>
              <div className="flex items-center gap-3 p-4">
                <p className="min-w-0 flex-1 text-sm font-semibold text-ink">
                  {item.product_name}
                </p>
                <ChevronRight
                  className="h-4 w-4 shrink-0 text-ink-3 transition group-hover:text-accent"
                  aria-hidden
                />
              </div>
            </Link>
          ))}
        </div>
      )}
    </AccountShell>
  );
}
