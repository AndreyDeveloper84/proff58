"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { Heart, List, Menu, Search, ShoppingCart, User } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCart } from "@/components/cart/CartProvider";
import { HOME_CONTENT } from "@/lib/home-content";
import { SITE } from "@/lib/site";
import { SearchBar } from "./SearchBar";

const ACCOUNT_ICONS: Record<string, LucideIcon> = {
  "Личный кабинет": User,
  Избранное: Heart,
};

interface HeaderProps {
  logoUrl?: string;
  siteName?: string;
}

export function Header({ logoUrl, siteName = "Профессионал" }: HeaderProps) {
  const { count } = useCart();
  const [open, setOpen] = useState(false);

  const logo = logoUrl ? (
    <Image
      src={logoUrl}
      alt={siteName}
      width={180}
      height={44}
      className="h-9 w-auto object-contain lg:h-11"
      priority
    />
  ) : (
    <span className="flex items-center gap-1.5 lg:gap-2">
      <Image
        src="/brands/professional-mark.png"
        alt=""
        width={44}
        height={44}
        className="h-7 w-auto shrink-0 object-contain sm:h-8 lg:h-11"
        aria-hidden
      />
      <span className="flex flex-col leading-none">
        <span className="font-display text-xs font-bold uppercase tracking-wide text-header-ink sm:text-sm lg:text-xl">
          {siteName}
        </span>
        <span className="mt-1 text-[6px] font-semibold text-accent sm:text-[7px] lg:text-[9px]">
          {SITE.brand.tagline}
        </span>
      </span>
    </span>
  );

  return (
    <header className="dark sticky top-0 z-40 border-b border-header-line bg-header">
      {/* PLP-01: одна компактная строка. На mobile остаются только основные действия. */}
      <div className="mx-auto flex h-16 w-full max-w-[1400px] items-center gap-2 px-4 lg:h-[72px] lg:gap-5">
        <button
          type="button"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-md text-header-ink hover:bg-header-ink/10 lg:hidden"
          aria-label="Меню"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>

        <Link href="/" className="min-w-0 shrink-0" aria-label="На главную">
          {logo}
        </Link>

        <Link
          href="/catalog"
          className="hidden h-11 shrink-0 items-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink transition hover:brightness-95 lg:inline-flex"
        >
          <List className="h-4 w-4" aria-hidden />
          Каталог
        </Link>

        <div data-theme="light" className="hidden min-w-0 flex-1 lg:block">
          <SearchBar
            className="max-w-none"
            placeholder="Поиск по товарам, брендам, категориям…"
          />
        </div>

        <a
          href={SITE.phone.href}
          className="hidden shrink-0 flex-col text-header-ink transition hover:text-accent xl:flex"
        >
          <span className="text-sm font-bold">{SITE.phone.display}</span>
          <span className="mt-1 text-[11px] font-normal text-footer-ink">{SITE.schedule}</span>
        </a>

        <Link
          href="/account/profile"
          className="hidden h-11 shrink-0 items-center gap-2 px-1 text-sm font-medium text-header-ink transition hover:text-accent lg:inline-flex"
        >
          <User className="h-5 w-5" aria-hidden />
          Мой кабинет
        </Link>

        <Link
          href="/search"
          className="ml-auto grid h-11 w-11 shrink-0 place-items-center rounded-md text-header-ink transition hover:bg-header-ink/10 lg:hidden"
          aria-label="Поиск"
        >
          <Search className="h-5 w-5" aria-hidden />
        </Link>

        <Link
          href="/cart"
          className="relative flex h-11 shrink-0 items-center justify-center gap-2 rounded-md px-2 text-header-ink transition hover:bg-header-ink/10"
          aria-label={count > 0 ? `Корзина, товаров: ${count}` : "Корзина"}
        >
          <ShoppingCart className="h-5 w-5" aria-hidden />
          <span className="hidden text-sm font-medium lg:inline">Корзина</span>
          {count > 0 && (
            <span className="absolute right-0 top-0 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-accent-ink lg:-right-1 lg:-top-1">
              {count > 99 ? "99+" : count}
            </span>
          )}
        </Link>
      </div>

      {/* Мобильное меню */}
      {open && (
        <div className="border-t border-header-line bg-header lg:hidden">
          <nav className="mx-auto flex max-w-[1400px] flex-col px-4 py-2">
            <Link
              href="/catalog"
              className="flex min-h-11 items-center gap-2 border-b border-header-line py-2.5 text-sm font-semibold text-header-ink hover:text-accent"
              onClick={() => setOpen(false)}
            >
              <List className="h-4 w-4" aria-hidden />
              Каталог
            </Link>
            {[...HOME_CONTENT.nav, ...HOME_CONTENT.account].map((l) => {
              const Icon = ACCOUNT_ICONS[l.label];
              return (
                <Link
                  key={l.label}
                  href={l.href}
                  className="flex min-h-11 items-center gap-2 border-b border-header-line py-2.5 text-sm text-footer-ink last:border-0 hover:text-accent"
                  onClick={() => setOpen(false)}
                >
                  {Icon && <Icon className="h-4 w-4" aria-hidden />}
                  {l.label}
                </Link>
              );
            })}
            <a
              href={SITE.phone.href}
              className="min-h-11 py-2.5 text-sm font-medium text-header-ink"
              onClick={() => setOpen(false)}
            >
              {SITE.phone.display}
            </a>
          </nav>
        </div>
      )}
    </header>
  );
}
