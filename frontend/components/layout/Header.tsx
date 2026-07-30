"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import {
  BarChart3,
  Clock3,
  Cog,
  Heart,
  List,
  MapPin,
  Menu,
  Phone,
  Search,
  ShieldCheck,
  ShoppingCart,
  Store,
  Truck,
  User,
  UserRound,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useCart } from "@/components/cart/CartProvider";
import { useCompare } from "@/lib/compare";
import { resolveStorefront, SITE, type ResolvedStorefront } from "@/lib/site";
import { SearchBar } from "./SearchBar";
import { ThemeToggle } from "./ThemeToggle";

interface HeaderProps {
  logoUrl?: string;
  siteName?: string;
  storefront?: ResolvedStorefront;
}

const TOP_LINK_ICONS: Record<string, LucideIcon> = {
  "Сервис и ремонт": Wrench,
  "Доставка и оплата": Truck,
  Гарантии: ShieldCheck,
  Контакты: Phone,
};

// Компактная двухуровневая шапка по утверждённому desktop-макету. Корзина и
// сравнение — рабочие; информационные страницы не превращаем в фиктивные
// ссылки, пока соответствующих маршрутов нет.
export function Header({
  logoUrl,
  siteName = "Профессионал",
  storefront = resolveStorefront(),
}: HeaderProps) {
  const { count } = useCart();
  const { count: compareCount } = useCompare();
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
    <span className="flex items-center gap-1.5">
      <span className="grid h-8 w-8 shrink-0 place-items-center text-accent">
        <Cog className="h-8 w-8" strokeWidth={3} aria-hidden />
      </span>
      <span className="flex flex-col leading-none">
        <span className="font-sans text-[15px] font-extrabold uppercase tracking-[0.02em] text-header-ink lg:text-[17px]">
          {siteName}
        </span>
        <span className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.04em] text-topbar-ink">
          {SITE.header.tagline}
        </span>
      </span>
    </span>
  );

  return (
    <header className="sticky top-0 z-40 border-b border-header-line bg-header text-header-ink">
      {/* Topbar — только desktop */}
      <div className="hidden border-b border-header-line bg-header lg:block">
        <div className="mx-auto flex h-8 max-w-[1400px] items-center justify-between px-4 text-[11px] text-topbar-ink">
          <div className="flex items-center gap-5">
            <span className="flex items-center gap-1.5 font-medium">
              <MapPin className="h-3.5 w-3.5 text-accent" aria-hidden />
              {storefront.region}
            </span>
            <span className="flex items-center gap-1.5 font-medium text-accent">
              <Store className="h-3.5 w-3.5" aria-hidden />
              {storefront.store}
            </span>
            {/* Инфо-пункты — не ссылки (страниц нет), но каждый раскрывает своё
                подменю по hover/фокусу: сюда переехала бывшая сервисная полоса
                главной. «Контакты» рендерятся из storefront (SiteSettings). */}
            {SITE.header.topLinks.map((l) => {
              const Icon = TOP_LINK_ICONS[l.label] ?? Wrench;
              const isContacts = l.label === "Контакты";
              return (
                <span
                  key={l.label}
                  tabIndex={0}
                  className="group relative flex cursor-default items-center gap-1.5 py-2 outline-none"
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden />
                  {l.label}
                  <span className="invisible absolute left-1/2 top-full z-50 w-64 -translate-x-1/2 rounded-md border border-header-line bg-header p-3 opacity-0 shadow-lg transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
                    {isContacts ? (
                      <span className="block space-y-1.5">
                        <span className="block text-xs font-semibold text-header-ink">
                          {storefront.address}
                        </span>
                        <a
                          href={storefront.phone.href}
                          className="block text-xs text-topbar-ink hover:text-accent"
                        >
                          {storefront.phone.display}
                        </a>
                        <a
                          href={`mailto:${storefront.email}`}
                          className="block text-xs text-topbar-ink hover:text-accent"
                        >
                          {storefront.email}
                        </a>
                        <span className="block text-xs text-topbar-ink">{storefront.schedule}</span>
                      </span>
                    ) : (
                      <span className="block space-y-2">
                        {l.menu.map((m) => (
                          <span key={m.title} className="block">
                            <span className="block text-xs font-semibold text-header-ink">
                              {m.title}
                            </span>
                            <span className="block text-[11px] leading-snug text-topbar-ink">
                              {m.text}
                            </span>
                          </span>
                        ))}
                      </span>
                    )}
                  </span>
                </span>
              );
            })}
          </div>
          {/* Справа в topbar: часы работы и сразу за ними — переключатель темы.
              В основной строке он стоял между поиском и телефоном и в этом ряду
              «кнопок покупки» читался как ещё одно действие с товаром. */}
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5">
              <Clock3 className="h-3.5 w-3.5" aria-hidden />
              {storefront.schedule}
            </span>
            <ThemeToggle className="h-6 w-6 text-topbar-ink hover:text-accent [&_svg]:h-3.5 [&_svg]:w-3.5" />
          </div>
        </div>
      </div>

      {/* Основная строка */}
      <div className="mx-auto flex h-14 w-full max-w-[1400px] items-center gap-2 px-4 lg:gap-4">
        <button
          type="button"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-md text-header-ink hover:bg-header-ink/10 lg:hidden"
          aria-label="Меню"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>

        <Link href="/" className="min-w-0 shrink-0 lg:w-[208px]" aria-label="На главную">
          {logo}
        </Link>

        <Link
          href="/catalog"
          className="hidden h-10 shrink-0 items-center gap-2 rounded-sm bg-accent px-5 text-[13px] font-semibold text-accent-ink transition hover:brightness-95 lg:inline-flex"
        >
          <List className="h-4 w-4" strokeWidth={2} aria-hidden />
          {SITE.header.catalogLabel}
        </Link>

        <div className="hidden min-w-0 flex-1 lg:block">
          <SearchBar
            className="max-w-none [&_form]:h-10 [&_input]:text-[13px]"
            placeholder={SITE.header.searchPlaceholder}
          />
        </div>

        <a
          href={storefront.phone.href}
          className="hidden shrink-0 flex-col text-header-ink transition hover:text-accent xl:flex"
        >
          <span className="text-[15px] font-bold leading-tight">{storefront.phone.display}</span>
          <span className="text-[11px] font-normal text-topbar-ink">{storefront.phoneNote}</span>
        </a>

        {/* Действия — desktop: избранное · сравнение (future) · корзина · кабинет */}
        <div className="ml-auto hidden shrink-0 items-center gap-1 lg:flex">
          <Link
            href="/account/wishlist"
            className="flex w-[68px] flex-col items-center gap-0.5 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label="Избранное"
          >
            <Heart className="h-5 w-5" aria-hidden />
            <span className="text-[11px]">Избранное</span>
          </Link>
          <Link
            href="/compare"
            className="relative flex w-[68px] flex-col items-center gap-0.5 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label={
              compareCount > 0 ? `Сравнение, товаров: ${compareCount}` : "Сравнение"
            }
          >
            <span className="relative">
              <BarChart3 className="h-5 w-5" aria-hidden />
              {compareCount > 0 && (
                <span className="absolute -right-2 -top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-accent-ink">
                  {compareCount}
                </span>
              )}
            </span>
            <span className="text-[11px]">Сравнение</span>
          </Link>
          <Link
            href="/cart"
            className="relative flex w-[68px] flex-col items-center gap-0.5 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label={count > 0 ? `Корзина, товаров: ${count}` : "Корзина"}
          >
            <span className="relative">
              <ShoppingCart className="h-5 w-5" aria-hidden />
              {count > 0 && (
                <span className="absolute -right-2 -top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold leading-none text-accent-ink">
                  {count > 99 ? "99+" : count}
                </span>
              )}
            </span>
            <span className="text-[11px]">Корзина</span>
          </Link>
          <Link
            href="/account/profile"
            className="flex w-[68px] flex-col items-center gap-0.5 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label="Личный кабинет"
          >
            <UserRound className="h-5 w-5" aria-hidden />
            <span className="text-[11px]">Кабинет</span>
          </Link>
        </div>

        {/* Действия — mobile/tablet: тема + поиск + корзина.
            Переключатель стоит в самой шапке, а не в бургер-меню: пункт, до
            которого надо сначала открыть меню, пользователь считает
            несуществующим. Ниже 640px его прячем — там логотип и две иконки уже
            занимают всю строку, третья вызывала бы горизонтальную прокрутку;
            на телефонах переключатель остаётся в меню. */}
        <div className="ml-auto flex shrink-0 items-center gap-2 lg:hidden">
          <ThemeToggle className="hidden sm:grid" />
          <Link
            href="/search"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-md text-header-ink transition hover:bg-header-ink/10"
            aria-label="Поиск"
          >
            <Search className="h-5 w-5" aria-hidden />
          </Link>
          <Link
            href="/cart"
            className="relative grid h-10 w-10 shrink-0 place-items-center rounded-md text-header-ink transition hover:bg-header-ink/10"
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
            {/* Телефон и тема — в одной строке. Переключатель здесь только для
                самых узких экранов (<640px), где в шапке места под него нет. */}
            <div className="flex items-center justify-between py-2.5 sm:hidden">
              <a href={storefront.phone.href} className="text-sm font-semibold text-header-ink">
                {storefront.phone.display}
              </a>
              <ThemeToggle />
            </div>
            <a
              href={storefront.phone.href}
              className="hidden min-h-11 items-center py-2.5 text-sm font-semibold text-header-ink sm:flex"
            >
              {storefront.phone.display}
            </a>
          </nav>
        </div>
      )}
    </header>
  );
}
