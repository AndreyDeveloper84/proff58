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
import { useAuthState } from "@/components/auth/AuthStateProvider";
import { useCart } from "@/components/cart/CartProvider";
import { useWishlist } from "@/components/wishlist/WishlistProvider";
import { accountLinkHref } from "@/lib/auth-state";
import type { InfoPageLink } from "@/lib/info-pages";
import { useCompare } from "@/lib/compare";
import { resolveStorefront, SITE, type ResolvedStorefront, type TopLink } from "@/lib/site";
import { cn } from "@/lib/utils";
import { CallLink, CopyContact } from "@/components/contacts/CopyContact";
import { SearchBar } from "./SearchBar";
import { ThemeToggle } from "./ThemeToggle";

interface HeaderProps {
  logoUrl?: string;
  siteName?: string;
  storefront?: ResolvedStorefront;
  /** Опубликованные страницы из админки — тот же список, что у подвала. */
  infoPages?: InfoPageLink[];
}

const INFO_PREFIX = "/info/";

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
  infoPages = [],
}: HeaderProps) {
  // Инфо-страницы ведутся в админке и заводятся черновиками. Пункт шапки
  // становится ссылкой, только когда его страница опубликована: ссылка на
  // черновик дала бы 404 из шапки — то есть на каждой странице сайта. Это то же
  // правило, по которому живёт подвал: отсутствующий раздел не подменяем.
  const publishedInfo = new Set(infoPages.map((page) => page.slug));
  const linkable = (href?: string): href is string =>
    !!href && (!href.startsWith(INFO_PREFIX) || publishedInfo.has(href.slice(INFO_PREFIX.length)));
  const { count } = useCart();
  const { count: compareCount } = useCompare();
  // Сердечко на карточке подтверждает клик только цветом самой карточки. Счётчик
  // в шапке — общий на весь сайт признак «выбор дошёл»: он же у сравнения и
  // корзины, и избранное без него читалось как менее надёжное.
  const { ids: wishlistIds } = useWishlist();
  const wishlistCount = wishlistIds.size;
  const [open, setOpen] = useState(false);
  // Гостя ведём сразу на форму входа: иначе он попадал в кабинет, откуда его
  // разворачивал серверный гвард, — со скачком адреса и пустой страницей. При
  // «может быть вошёл» ссылка идёт по назначению — см. lib/auth-state.
  const authState = useAuthState();
  const profileHref = accountLinkHref("/account/profile", authState);

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
      {/* min-w-0: на экране 320 px подпись под названием переносится на вторую строку,
          а не выталкивает иконки поиска и корзины за край (UX-04). */}
      <span className="flex min-w-0 flex-col leading-none">
        <span className="font-sans text-[15px] font-extrabold uppercase tracking-[0.02em] text-header-ink lg:text-[17px]">
          {siteName}
        </span>
        <span className="mt-0.5 text-xs font-medium uppercase leading-tight tracking-normal text-topbar-ink min-[360px]:whitespace-nowrap">
          {SITE.header.tagline}
        </span>
      </span>
    </span>
  );

  return (
    <header className="sticky top-0 z-40 border-b border-header-line bg-header text-header-ink">
      {/* Topbar — только desktop */}
      <div className="hidden border-b border-header-line bg-header lg:block">
        <div className="mx-auto flex h-9 w-full max-w-[1680px] items-center justify-between px-4 text-xs text-topbar-ink sm:px-6 xl:px-8">
          <div className="flex items-center gap-5">
            <span className="flex items-center gap-1.5 font-medium">
              <MapPin className="h-3.5 w-3.5 text-accent" aria-hidden />
              {storefront.region}
            </span>
            {/* UX-03: подпись короткая, а в буфер уходит полный адрес магазина. */}
            <CopyContact
              kind="address"
              value={storefront.address}
              className="flex items-center gap-1.5 font-medium text-accent hover:brightness-90"
            >
              <Store className="h-3.5 w-3.5" aria-hidden />
              {storefront.store}
            </CopyContact>
            {/* Инфо-пункты: каждый раскрывает подсказку по hover/фокусу — сюда
                переехала бывшая сервисная полоса главной — и ведёт на свою страницу,
                если она опубликована. «Контакты» рендерятся из storefront
                (SiteSettings) и ведут на «О компании», где адрес и карта. */}
            {(SITE.header.topLinks as readonly TopLink[]).map((l) => {
              const Icon = TOP_LINK_ICONS[l.label] ?? Wrench;
              const isContacts = l.label === "Контакты";
              const href = linkable(l.href) ? l.href : undefined;
              return (
                <span
                  key={l.label}
                  // Ссылка сама попадает в таб-порядок и открывает подсказку через
                  // group-focus-within; лишний tabIndex дал бы вторую остановку на
                  // одном пункте. Без ссылки он остаётся единственным способом
                  // добраться до подсказки с клавиатуры.
                  tabIndex={href ? undefined : 0}
                  className={cn(
                    "group relative flex items-center gap-1.5 py-2 outline-none",
                    !href && "cursor-default",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden />
                  {/* Ссылка — сам ярлык, а не обёртка: внутри подсказки уже есть
                      ссылки (телефон, почта), и вложенные <a> — невалидная разметка. */}
                  {href ? (
                    <Link href={href} className="hover:text-accent">
                      {l.label}
                    </Link>
                  ) : (
                    l.label
                  )}
                  <span className="invisible absolute left-1/2 top-full z-50 w-72 -translate-x-1/2 rounded-md border border-header-line bg-header p-4 opacity-0 shadow-lg transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
                    {isContacts ? (
                      <span className="block space-y-1.5">
                        <CopyContact
                          kind="address"
                          value={storefront.address}
                          className="block text-sm font-semibold text-header-ink"
                        />
                        <span className="flex items-center justify-between gap-3">
                          <CopyContact
                            kind="phone"
                            value={storefront.phone.display}
                            className="text-sm text-topbar-ink"
                          />
                          <CallLink href={storefront.phone.href} className="text-sm" />
                        </span>
                        <a
                          href={`mailto:${storefront.email}`}
                          className="block text-sm text-topbar-ink hover:text-accent"
                        >
                          {storefront.email}
                        </a>
                        <span className="block text-sm text-topbar-ink">{storefront.schedule}</span>
                      </span>
                    ) : (
                      <span className="block space-y-2">
                        {l.menu.map((m) => (
                          <span key={m.title} className="block">
                            {linkable(m.href) ? (
                              <Link
                                href={m.href}
                                className="block text-sm font-semibold text-header-ink hover:text-accent"
                              >
                                {m.title}
                              </Link>
                            ) : (
                              <span className="block text-sm font-semibold text-header-ink">
                                {m.title}
                              </span>
                            )}
                            <span className="block text-xs leading-snug text-topbar-ink">
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
      <div className="mx-auto flex h-16 w-full max-w-[1680px] items-center gap-2 px-4 sm:px-6 lg:gap-4 xl:px-8">
        <button
          type="button"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-md text-header-ink hover:bg-header-ink/10 lg:hidden"
          aria-label="Меню"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <Menu className="h-5 w-5" aria-hidden />
        </button>

        <Link href="/" className="min-w-0 shrink lg:w-[228px] lg:shrink-0" aria-label="На главную">
          {logo}
        </Link>

        <Link
          href="/catalog"
          className="hidden h-11 shrink-0 items-center gap-2 rounded-sm bg-accent px-5 text-sm font-semibold text-accent-ink transition hover:brightness-95 lg:inline-flex"
        >
          <List className="h-4 w-4" strokeWidth={2} aria-hidden />
          {SITE.header.catalogLabel}
        </Link>

        <div className="hidden min-w-0 flex-1 lg:block">
          <SearchBar
            className="max-w-none [&_form]:h-11 [&_input]:text-base"
            placeholder={SITE.header.searchPlaceholder}
          />
        </div>

        {/* UX-03: нажатие на номер копирует его; звонок — отдельной ссылкой рядом. */}
        <div className="hidden shrink-0 flex-col text-header-ink xl:flex">
          <CopyContact
            kind="phone"
            value={storefront.phone.display}
            className="text-base font-bold leading-tight"
          />
          <span className="flex items-center gap-2 text-xs leading-tight">
            <CallLink href={storefront.phone.href} />
            {storefront.phoneNote ? (
              <span className="font-normal text-topbar-ink">{storefront.phoneNote}</span>
            ) : null}
          </span>
        </div>

        {/* Действия — desktop: избранное · сравнение (future) · корзина · кабинет */}
        <div className="ml-auto hidden shrink-0 items-center gap-1 lg:flex">
          <Link
            href="/wishlist"
            className="relative flex w-[68px] flex-col items-center gap-0.5 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label={
              wishlistCount > 0 ? `Избранное, товаров: ${wishlistCount}` : "Избранное"
            }
          >
            <span className="relative">
              <Heart className="h-5 w-5" aria-hidden />
              {wishlistCount > 0 && (
                <span className="absolute -right-2 -top-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-accent px-1 text-[11px] font-bold leading-none text-accent-ink">
                  {wishlistCount > 99 ? "99+" : wishlistCount}
                </span>
              )}
            </span>
            <span className="text-xs">Избранное</span>
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
                <span className="absolute -right-2 -top-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-accent px-1 text-[11px] font-bold leading-none text-accent-ink">
                  {compareCount}
                </span>
              )}
            </span>
            <span className="text-xs">Сравнение</span>
          </Link>
          <Link
            href="/cart"
            className="relative flex w-[68px] flex-col items-center gap-0.5 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label={count > 0 ? `Корзина, товаров: ${count}` : "Корзина"}
          >
            <span className="relative">
              <ShoppingCart className="h-5 w-5" aria-hidden />
              {count > 0 && (
                <span className="absolute -right-2 -top-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-accent px-1 text-[11px] font-bold leading-none text-accent-ink">
                  {count > 99 ? "99+" : count}
                </span>
              )}
            </span>
            <span className="text-xs">Корзина</span>
          </Link>
          <Link
            href={profileHref}
            className="flex w-[68px] flex-col items-center gap-0.5 rounded-md py-1 text-header-ink transition hover:text-accent"
            aria-label="Личный кабинет"
          >
            <UserRound className="h-5 w-5" aria-hidden />
            <span className="text-xs">Кабинет</span>
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
              <span className="absolute right-1 top-1 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-accent px-1 text-[11px] font-bold leading-none text-accent-ink">
                {count > 99 ? "99+" : count}
              </span>
            )}
          </Link>
        </div>
      </div>

      {/* Мобильное меню */}
      {open && (
        <div className="border-t border-header-line bg-header lg:hidden">
          <nav className="mx-auto flex w-full max-w-[1680px] flex-col px-4 py-2 sm:px-6">
            <Link
              href="/catalog"
              className="flex min-h-11 items-center gap-2 border-b border-header-line py-2.5 text-sm font-semibold text-header-ink hover:text-accent"
              onClick={() => setOpen(false)}
            >
              <List className="h-4 w-4" aria-hidden />
              {SITE.header.catalogLabel}
            </Link>
            <Link
              href={profileHref}
              className="flex min-h-11 items-center gap-2 border-b border-header-line py-2.5 text-sm text-topbar-ink hover:text-accent"
              onClick={() => setOpen(false)}
            >
              <User className="h-4 w-4" aria-hidden />
              Личный кабинет
            </Link>
            <Link
              href="/wishlist"
              className="flex min-h-11 items-center gap-2 border-b border-header-line py-2.5 text-sm text-topbar-ink hover:text-accent"
              onClick={() => setOpen(false)}
              aria-label={
                wishlistCount > 0 ? `Избранное, товаров: ${wishlistCount}` : undefined
              }
            >
              <Heart className="h-4 w-4" aria-hidden />
              Избранное
              {wishlistCount > 0 && (
                <span className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-accent px-1 text-[11px] font-bold leading-none text-accent-ink">
                  {wishlistCount > 99 ? "99+" : wishlistCount}
                </span>
              )}
            </Link>
            {/* #592: инфо-пункты (сервис/доставка/гарантии/контакты) в мобильном
                меню не показываем, пока нет страниц — некликабельные строки в
                меню бесполезны, битые ссылки запрещены DoD эпика. */}
            {/* Телефон и тема — в одной строке. Переключатель здесь только для
                самых узких экранов (<640px), где в шапке места под него нет. */}
            <div className="flex min-h-11 items-center justify-between gap-3 py-2.5">
              <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <CopyContact
                  kind="phone"
                  value={storefront.phone.display}
                  className="min-h-11 text-base font-semibold text-header-ink"
                />
                <CallLink href={storefront.phone.href} className="inline-flex min-h-11 items-center text-sm" />
              </span>
              <span className="sm:hidden">
                <ThemeToggle />
              </span>
            </div>
            <CopyContact
              kind="address"
              value={storefront.address}
              className="min-h-11 py-2 text-sm text-topbar-ink"
            />
          </nav>
        </div>
      )}
    </header>
  );
}
