"use client";

import Link from "next/link";
import {
  CircleUserRound,
  LayoutGrid,
  Package,
  ShoppingCart,
  UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";

type MobileNavSection = "home" | "catalog" | "account" | "cart" | "profile";

const ITEMS = [
  { section: "home", label: "Главная", href: "/", icon: LayoutGrid },
  { section: "catalog", label: "Каталог", href: "/catalog", icon: Package },
  { section: "account", label: "Кабинет", href: "/account/profile", icon: UserRound },
  { section: "cart", label: "Корзина", href: "/cart", icon: ShoppingCart },
  {
    section: "profile",
    label: "Профиль",
    href: "/account/profile#personal-data",
    icon: CircleUserRound,
  },
] as const;

export function MobileBottomNav({ active }: { active: MobileNavSection }) {
  return (
    <nav
      aria-label="Мобильная навигация"
      className="fixed inset-x-0 bottom-0 z-50 grid h-[68px] grid-cols-5 border-t border-line bg-surface px-1 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_24px_rgba(20,24,27,0.08)] lg:hidden"
    >
      {ITEMS.map((item) => {
        const Icon = item.icon;
        const current = item.section === active;
        return (
          <Link
            key={item.section}
            href={item.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "flex min-w-0 flex-col items-center justify-center gap-1 text-[10px] font-medium",
              current ? "text-accent" : "text-ink-3",
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
