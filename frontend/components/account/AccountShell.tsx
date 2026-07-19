"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  ChevronLeft,
  CircleUserRound,
  ClipboardList,
  GitCompare,
  Heart,
  Home,
  LayoutGrid,
  MapPin,
  Package,
  RefreshCcw,
  ShoppingCart,
  UserRound,
  WalletCards,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { SITE } from "@/lib/site";
import { cn } from "@/lib/utils";

type AccountShellProps = {
  title: string;
  children: React.ReactNode;
  mobileBackHref?: string;
};

type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  match?: string;
};

const PRIMARY_NAV: NavItem[] = [
  { label: "Главная", href: "/account/profile", icon: Home, match: "/account/profile" },
  { label: "Заказы", href: "/account/orders", icon: ClipboardList, match: "/account/orders" },
  { label: "Избранное", href: "/account/wishlist", icon: Heart, match: "/account/wishlist" },
  {
    label: "Сравнение",
    href: "/account/profile#comparison",
    icon: GitCompare,
  },
  { label: "Возвраты и заявки", href: "/account/orders", icon: RefreshCcw },
];

const SETTINGS_NAV: NavItem[] = [
  {
    label: "Личные данные",
    href: "/account/profile#personal-data",
    icon: UserRound,
  },
  { label: "Адреса доставки", href: "/account/profile#addresses", icon: MapPin },
  { label: "Способы оплаты", href: "/account/profile#payment-methods", icon: WalletCards },
  {
    label: "Уведомления",
    href: "/account/notifications",
    icon: Bell,
    match: "/account/notifications",
  },
  {
    label: "Профиль компании",
    href: "/account/profile#company-profile",
    icon: CircleUserRound,
  },
];

function SidebarLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium transition",
        active
          ? "bg-accent/10 text-accent"
          : "text-ink-2 hover:bg-raised hover:text-ink",
      )}
    >
      <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
      {item.label}
    </Link>
  );
}

function AccountSidebar({ pathname }: { pathname: string }) {
  const isActive = (item: NavItem) =>
    Boolean(item.match && (pathname === item.match || pathname.startsWith(`${item.match}/`)));

  return (
    <aside className="hidden lg:block">
      <nav
        aria-label="Разделы личного кабинета"
        className="rounded-lg border border-line bg-surface p-3"
      >
        <div className="space-y-1">
          {PRIMARY_NAV.map((item) => (
            <SidebarLink key={item.label} item={item} active={isActive(item)} />
          ))}
        </div>
        <div className="my-3 border-t border-line" />
        <div className="space-y-1">
          {SETTINGS_NAV.map((item) => (
            <SidebarLink key={item.label} item={item} active={isActive(item)} />
          ))}
        </div>
      </nav>

      <div className="mt-5 rounded-lg border border-line bg-surface p-4">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-line bg-raised">
            <span className="text-lg" aria-hidden>
              ◔
            </span>
          </div>
          <div>
            <p className="text-sm font-semibold text-ink">Нужна помощь?</p>
            <p className="mt-1 text-xs leading-5 text-ink-3">
              Напишите специалисту в MAX. Подберём инструмент под вашу задачу.
            </p>
          </div>
        </div>
        <a
          href={SITE.support.max.href}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 flex h-11 w-full items-center justify-center gap-2 rounded-md bg-header px-4 text-sm font-semibold text-header-ink transition hover:brightness-125"
        >
          Написать в MAX
          <Image
            src="/brands/max-colored.png"
            alt=""
            width={22}
            height={22}
            className="h-[22px] w-[22px]"
            aria-hidden
          />
        </a>
      </div>
    </aside>
  );
}

const MOBILE_NAV = [
  { label: "Главная", href: "/", icon: LayoutGrid },
  { label: "Каталог", href: "/catalog", icon: Package },
  { label: "Кабинет", href: "/account/profile", icon: UserRound },
  { label: "Корзина", href: "/cart", icon: ShoppingCart },
  { label: "Профиль", href: "/account/profile#personal-data", icon: CircleUserRound },
] as const;

function MobileAccountNav() {
  return (
    <nav
      aria-label="Мобильная навигация"
      className="fixed inset-x-0 bottom-0 z-50 grid h-[68px] grid-cols-5 border-t border-line bg-surface px-1 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_24px_rgba(20,24,27,0.08)] lg:hidden"
    >
      {MOBILE_NAV.map((item) => {
        const Icon = item.icon;
        const active = item.label === "Кабинет";
        return (
          <Link
            key={item.label}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-w-0 flex-col items-center justify-center gap-1 text-[10px] font-medium",
              active ? "text-accent" : "text-ink-3",
            )}
          >
            <Icon className="h-5 w-5" aria-hidden />
            <span className="truncate">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function AccountShell({ title, children, mobileBackHref }: AccountShellProps) {
  const pathname = usePathname();

  return (
    <main className="min-h-[70vh] bg-canvas pb-20 lg:pb-0">
      <div className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
        <nav
          aria-label="Хлебные крошки"
          className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex"
        >
          <Link href="/" className="hover:text-accent">
            Главная
          </Link>
          <span aria-hidden>›</span>
          <span>Личный кабинет</span>
          {title !== "Личный кабинет" && (
            <>
              <span aria-hidden>›</span>
              <span>{title}</span>
            </>
          )}
        </nav>

        <div className="mb-4 flex min-h-9 items-center gap-2 lg:mb-5">
          {mobileBackHref && (
            <Link
              href={mobileBackHref}
              aria-label="Назад"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-md text-ink lg:hidden"
            >
              <ChevronLeft className="h-5 w-5" aria-hidden />
            </Link>
          )}
          <h1 className="font-display text-2xl font-semibold text-ink lg:text-[28px]">
            {title}
          </h1>
        </div>

        <div className="grid items-start gap-6 lg:grid-cols-[250px_minmax(0,1fr)]">
          <AccountSidebar pathname={pathname} />
          <div className="min-w-0">{children}</div>
        </div>
      </div>
      <MobileAccountNav />
    </main>
  );
}
