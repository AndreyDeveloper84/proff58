"use client";

import Link from "next/link";
import {
  Search,
  Package,
  ShoppingCart,
  UserRound,
} from "lucide-react";
import { accountLinkHref, useHasAuthMarker } from "@/lib/auth-marker";
import { cn } from "@/lib/utils";

type MobileNavSection = "catalog" | "search" | "account" | "cart" | "profile";

const ITEMS = [
  { section: "catalog", label: "Каталог", href: "/catalog", icon: Package },
  { section: "search", label: "Поиск", href: "/search", icon: Search },
  { section: "cart", label: "Корзина", href: "/cart", icon: ShoppingCart },
  {
    section: "profile",
    label: "Профиль",
    href: "/account/profile",
    icon: UserRound,
  },
] as const;

export function MobileBottomNav({ active }: { active: MobileNavSection }) {
  // Гостю «Профиль» ведёт на форму входа, а не в кабинет: иначе его разворачивал
  // бы серверный гвард — со скачком адреса и пустой страницей.
  const authMarker = useHasAuthMarker();

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
              item.section === "profile" ? accountLinkHref(item.href, authMarker) : item.href
            }
            aria-current={current ? "page" : undefined}
            className={cn(
              "flex min-w-0 flex-col items-center justify-center gap-1 text-[10px] font-medium",
              current ||
                (active === "account" && item.section === "profile")
                ? "text-accent"
                : "text-ink-3",
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
