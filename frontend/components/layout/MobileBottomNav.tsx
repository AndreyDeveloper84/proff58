"use client";

import Link from "next/link";
import { Package, Search } from "lucide-react";
import { useAuthState } from "@/components/auth/AuthStateProvider";
import { accountLinkHref } from "@/lib/auth-state";
import { cn } from "@/lib/utils";
import {
  AccountActionIcon,
  ACTION_DURATION_MS,
  CartActionIcon,
  usePulse,
} from "./HeaderActionIcons";

type MobileNavSection = "catalog" | "search" | "account" | "cart" | "profile";

// Корзина и профиль — те же анимируемые иконки, что в шапке (рисунок lucide
// прежний): корзина отыгрывает успешное добавление, профиль кивает при нажатии.
const ITEMS = [
  { section: "catalog", label: "Каталог", href: "/catalog", icon: Package },
  { section: "search", label: "Поиск", href: "/search", icon: Search },
  { section: "cart", label: "Корзина", href: "/cart", icon: null },
  { section: "profile", label: "Профиль", href: "/account/profile", icon: null },
] as const;

export function MobileBottomNav({ active }: { active: MobileNavSection }) {
  // Гостю «Профиль» ведёт на форму входа, а не в кабинет: иначе его разворачивал
  // бы серверный гвард — со скачком адреса и пустой страницей.
  const authState = useAuthState();
  const accountPulse = usePulse(ACTION_DURATION_MS.account);

  return (
    <nav
      aria-label="Мобильная навигация"
      className="fixed inset-x-0 bottom-0 z-50 grid h-[64px] grid-cols-4 border-t border-line bg-surface px-2 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_24px_rgba(20,24,27,0.08)] lg:hidden"
    >
      {ITEMS.map((item) => {
        const Icon = item.icon;
        const current = item.section === active;
        return (
          <Link
            key={item.section}
            href={
              item.section === "profile" ? accountLinkHref(item.href, authState) : item.href
            }
            aria-current={current ? "page" : undefined}
            onClick={item.section === "profile" ? accountPulse.fire : undefined}
            className={cn(
              "hdr-action flex min-w-0 flex-col items-center justify-center gap-1 text-xs font-medium",
              current ||
                (active === "account" && item.section === "profile")
                ? "text-accent"
                : "text-ink-3",
            )}
          >
            {item.section === "cart" ? (
              <CartActionIcon className="h-5 w-5" />
            ) : item.section === "profile" ? (
              <AccountActionIcon className="h-5 w-5" pulse={accountPulse} />
            ) : Icon ? (
              <Icon className="h-5 w-5" aria-hidden />
            ) : null}
            <span className="truncate">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
