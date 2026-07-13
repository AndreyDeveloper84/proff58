"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { Heart, Menu, Scale, ShoppingCart, User } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCart } from "@/components/cart/CartProvider";
import { HOME_CONTENT } from "@/lib/home-content";
import { SearchBar } from "./SearchBar";

const ACCOUNT_ICONS: Record<string, LucideIcon> = {
  "Личный кабинет": User,
  Избранное: Heart,
  Сравнение: Scale,
};

interface HeaderProps {
  logoUrl?: string;
  siteName?: string;
}

export function Header({ logoUrl, siteName = "Профессионал" }: HeaderProps) {
  const { count } = useCart();
  const [open, setOpen] = useState(false);

  // #477: шапка — тёмная брендовая рамка (класс dark → dark-токены в поддереве).
  return (
    <header className="dark sticky top-0 z-40 border-b border-line bg-canvas/95 backdrop-blur">
      {/* Топ-бар: промо + телефон + аккаунт-ссылки (скрыт на мобиле) */}
      <div className="hidden border-b border-line/60 lg:block">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-1.5 text-xs text-ink-3 sm:px-6 lg:px-8">
          <span>{HOME_CONTENT.topbar.promo}</span>
          <div className="flex items-center gap-5">
            <a
              href={HOME_CONTENT.topbar.phoneHref}
              className="font-medium text-ink-2 hover:text-ink"
            >
              {HOME_CONTENT.topbar.phone}
            </a>
            {HOME_CONTENT.account.map((l) => (
              <Link key={l.label} href={l.href} className="transition hover:text-ink">
                {l.label}
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Основная строка: бургер + лого + поиск + иконки */}
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <button
          type="button"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-raised lg:hidden"
          aria-label="Меню"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>
        <Link href="/" className="shrink-0">
          {logoUrl ? (
            <Image
              src={logoUrl}
              alt={siteName}
              width={140}
              height={40}
              className="h-10 w-auto object-contain"
              priority
            />
          ) : (
            <span className="font-display text-xl font-bold uppercase tracking-wide text-accent">
              {siteName}
            </span>
          )}
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

      {/* Нав-меню (десктоп) */}
      <nav className="hidden border-t border-line/60 lg:block">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-2 text-sm sm:px-6 lg:px-8">
          {HOME_CONTENT.nav.map((l) => (
            <Link key={l.label} href={l.href} className="text-ink-2 transition hover:text-accent">
              {l.label}
            </Link>
          ))}
        </div>
      </nav>

      {/* Мобильное меню */}
      {open && (
        <div className="border-t border-line bg-surface lg:hidden">
          <nav className="mx-auto flex max-w-7xl flex-col px-4 py-2 sm:px-6">
            {[...HOME_CONTENT.nav, ...HOME_CONTENT.account].map((l) => {
              const Icon = ACCOUNT_ICONS[l.label];
              return (
                <Link
                  key={l.label}
                  href={l.href}
                  className="flex items-center gap-2 border-b border-line/40 py-2.5 text-sm text-ink-2 last:border-0 hover:text-accent"
                  onClick={() => setOpen(false)}
                >
                  {Icon && <Icon className="h-4 w-4" aria-hidden />}
                  {l.label}
                </Link>
              );
            })}
            <a
              href={HOME_CONTENT.topbar.phoneHref}
              className="py-2.5 text-sm font-medium text-ink"
              onClick={() => setOpen(false)}
            >
              {HOME_CONTENT.topbar.phone}
            </a>
          </nav>
        </div>
      )}
    </header>
  );
}
