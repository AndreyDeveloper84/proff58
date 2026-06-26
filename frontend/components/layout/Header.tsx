"use client";

import Link from "next/link";
import { ShoppingCart, LayoutGrid } from "lucide-react";
import { useCart } from "@/components/cart/CartProvider";
import { SITE } from "@/lib/site";
import { TopBar } from "./TopBar";
import { SearchBar } from "./SearchBar";

export function Header() {
  const { count } = useCart();

  return (
    <header className="sticky top-0 z-40 bg-canvas/95 backdrop-blur">
      <TopBar />
      <div className="border-b border-line">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <Link href="/" className="shrink-0 leading-tight">
            <span className="block font-display text-xl font-bold uppercase tracking-wide text-accent">
              {SITE.brand.name}
            </span>
            <span className="hidden text-[10px] uppercase tracking-wide text-ink-3 sm:block">
              {SITE.brand.tagline}
            </span>
          </Link>

          <Link
            href="/catalog"
            className="hidden shrink-0 items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:opacity-90 sm:flex"
          >
            <LayoutGrid className="h-4 w-4" aria-hidden />
            Весь каталог
          </Link>

          <div className="flex-1">
            <SearchBar />
          </div>

          <Link
            href="/cart"
            className="relative grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-2 transition hover:bg-raised hover:text-ink"
            aria-label={count > 0 ? `Корзина, товаров: ${count}` : "Корзина"}
          >
            <ShoppingCart className="h-5 w-5" aria-hidden />
            {count > 0 && (
              <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-accent-ink">
                {count > 99 ? "99+" : count}
              </span>
            )}
          </Link>
        </div>
      </div>
    </header>
  );
}
