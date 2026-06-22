"use client";

import { ShoppingCart } from "lucide-react";
import { SearchBar } from "./SearchBar";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <a
          href="/"
          className="shrink-0 font-display text-xl font-bold uppercase tracking-wide text-accent"
        >
          Профессионал
        </a>
        <div className="flex-1">
          <SearchBar />
        </div>
        <a
          href="/cart"
          className="relative grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-2 transition hover:bg-raised hover:text-ink"
          aria-label="Корзина"
        >
          <ShoppingCart className="h-5 w-5" />
        </a>
      </div>
    </header>
  );
}
