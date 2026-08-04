"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  ChevronLeft,
  ClipboardList,
  FileText,
  Heart,
  Home,
  MapPin,
  Star,
  UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
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
  // #560: счета юрлица (24ч, эпик #557). Пункт виден всем — B2C увидит пустое
  // состояние с пояснением (тип покупателя в Shell не прокидывается).
  { label: "Счета", href: "/account/invoices", icon: FileText, match: "/account/invoices" },
  // Избранное живёт на витрине (/wishlist) — оно доступно и без аккаунта.
  { label: "Избранное", href: "/wishlist", icon: Heart, match: "/wishlist" },
  // #573: отзывы; страница сама показывает off/empty-состояния (прецедент — «Счета»).
  { label: "Отзывы", href: "/account/reviews", icon: Star, match: "/account/reviews" },
];

const SETTINGS_NAV: NavItem[] = [
  {
    label: "Личные данные",
    href: "/account/profile#personal-data",
    icon: UserRound,
  },
  { label: "Адрес доставки", href: "/account/profile#addresses", icon: MapPin },
  {
    label: "Уведомления",
    href: "/account/notifications",
    icon: Bell,
    match: "/account/notifications",
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
    </aside>
  );
}

export function AccountShell({ title, children, mobileBackHref }: AccountShellProps) {
  const pathname = usePathname();

  return (
    <main className="min-h-[70vh] bg-canvas pb-20 lg:pb-0">
      <div className="mx-auto w-full max-w-[1480px] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
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
      <MobileBottomNav active="account" />
    </main>
  );
}
