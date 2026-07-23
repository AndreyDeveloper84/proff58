"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import {
  BarChart3,
  Clock3,
  Heart,
  List,
  MapPin,
  Menu,
  Search,
  ShoppingCart,
  User,
} from "lucide-react";
import { useCart } from "@/components/cart/CartProvider";
import { SITE } from "@/lib/site";
import { SearchBar } from "./SearchBar";
import { ThemeToggle } from "./ThemeToggle";

interface HeaderProps {
  logoUrl?: string;
  siteName?: string;
}

// #586: светлый e-commerce header по утверждённому макету главной. Две строки на
// desktop — topbar (регион/магазин/инфо + график + переключатель темы) и основная
// строка (лого · «Каталог товаров» · поиск · телефон · избранное/сравнение/корзина).
// Следует за темой через токены (bg-header/bg-topbar светлые в светлой теме, тёмные
// в тёмной). На mobile — компактная строка (бургер · лого · поиск · корзина).
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
    <span className="flex items-center gap-2">
      <Image
        src="/brands/professional-mark.png"
        alt=""
        width={44}
        height={44}
        className="h-8 w-auto shrink-0 object-contain lg:h-10"
        aria-hidden
      />
      <span className="flex flex-col leading-none">
        <span className="font-display text-base font-bold uppercase tracking-wide text-header-ink lg:text-xl">
          {siteName}
        </span>
        <span className="mt-1 text-[9px] font-medium text-topbar-ink lg:text-[11px]">
          {SITE.header.tagline}
        </span>
      </span>
    </span>
  );

  return (
    <header className="sticky top-0 z-40 border-b border-header-line bg-header">
      {/* Topbar — только desktop */}
      <div className="hidden border-b border-header-line bg-topbar lg:block">
        <div className="mx-auto flex h-9 max-w-[1400px] items-center justify-between px-4 text-xs text-topbar-ink">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-medium text-header-ink">
              <MapPin className="h-3.5 w-3.5 text-accent" aria-hidden />
              {SITE.region}
            </span>
            <span className="text-topbar-ink">{SITE.header.store}</span>
            {/* #592: инфо-страниц (/service, /delivery, …) на сайте пока нет —
                пункты показаны как future-текст, а не битые ссылки. Станут
                ссылками вместе со статическими страницами. */}
            {SITE.header.topLinks.map((l) => (
              <span key={l.label} className="cursor-default" title="Раздел скоро появится">
                {l.label}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5">
              <Clock3 className="h-3.5 w-3.5" aria-hidden />
              {SITE.schedule}
            </span>
            <ThemeToggle className="h-7 w-7" />
          </div>
        </div>
      </div>

      {/* Основная строка */}
      <div className="mx-auto flex h-16 w-full max-w-[1400px] items-center gap-2 px-4 lg:h-[76px] lg:gap-5">
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
          {SITE.header.catalogLabel}
        </Link>

        <div className="hidden min-w-0 flex-1 lg:block">
          <SearchBar className="max-w-none" placeholder={SITE.header.searchPlaceholder} />
        </div>

        <a
          href={SITE.phone.href}
          className="hidden shrink-0 flex-col text-header-ink transition hover:text-accent xl:flex"
        >
          <span className="text-base font-bold leading-tight">{SITE.phone.display}</span>
          <span className="text-[11px] font-normal text-topbar-ink">{SITE.phoneNote}</span>
        </a>

        {/* Действия — desktop: избранное · сравнение (future) · корзина */}
        <div className="ml-auto hidden shrink-0 items-center gap-1 lg:flex">
          <Link
            href="/account/wishlist"
            className="flex w-16 flex-col items-center gap-1 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label="Избранное"
          >
            <Heart className="h-[22px] w-[22px]" aria-hidden />
            <span className="text-[11px]">Избранное</span>
          </Link>
          {/* Сравнение — Wave 2, страницы пока нет: неактивно, без мёртвой ссылки. */}
          <span
            className="flex w-16 cursor-default flex-col items-center gap-1 rounded-md py-1 text-topbar-ink/60"
            aria-disabled="true"
            title="Скоро"
          >
            <BarChart3 className="h-[22px] w-[22px]" aria-hidden />
            <span className="text-[11px]">Сравнение</span>
          </span>
          <Link
            href="/cart"
            className="relative flex w-16 flex-col items-center gap-1 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label={count > 0 ? `Корзина, товаров: ${count}` : "Корзина"}
          >
            <span className="relative">
              <ShoppingCart className="h-[22px] w-[22px]" aria-hidden />
              {count > 0 && (
                <span className="absolute -right-2 -top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-accent-ink">
                  {count > 99 ? "99+" : count}
                </span>
              )}
            </span>
            <span className="text-[11px]">Корзина</span>
          </Link>
        </div>

        {/* Действия — mobile: поиск + корзина */}
        <Link
          href="/search"
          className="ml-auto grid h-11 w-11 shrink-0 place-items-center rounded-md text-header-ink transition hover:bg-header-ink/10 lg:hidden"
          aria-label="Поиск"
        >
          <Search className="h-5 w-5" aria-hidden />
        </Link>
        <Link
          href="/cart"
          className="relative grid h-11 w-11 shrink-0 place-items-center rounded-md text-header-ink transition hover:bg-header-ink/10 lg:hidden"
          aria-label={count > 0 ? `Корзина, товаров: ${count}` : "Корзина"}
        >
          <ShoppingCart className="h-5 w-5" aria-hidden />
          {count > 0 && (
            <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-accent-ink">
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
              {SITE.header.catalogLabel}
            </Link>
            <Link
              href="/account/profile"
              className="flex min-h-11 items-center gap-2 border-b border-header-line py-2.5 text-sm text-topbar-ink hover:text-accent"
              onClick={() => setOpen(false)}
            >
              <User className="h-4 w-4" aria-hidden />
              Личный кабинет
            </Link>
            <Link
              href="/account/wishlist"
              className="flex min-h-11 items-center gap-2 border-b border-header-line py-2.5 text-sm text-topbar-ink hover:text-accent"
              onClick={() => setOpen(false)}
            >
              <Heart className="h-4 w-4" aria-hidden />
              Избранное
            </Link>
            {/* #592: инфо-пункты (сервис/доставка/гарантии/контакты) в мобильном
                меню не показываем, пока нет страниц — некликабельные строки в
                меню бесполезны, битые ссылки запрещены DoD эпика. */}
            <div className="flex items-center justify-between py-2.5">
              <a href={SITE.phone.href} className="text-sm font-semibold text-header-ink">
                {SITE.phone.display}
              </a>
              <ThemeToggle />
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
