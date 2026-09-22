"use client";

// Иконки действий шапки с микроанимациями: избранное, сравнение, корзина, кабинет.
//
// Два уровня движения живут на РАЗНЫХ элементах, чтобы transform не спорили:
//   .hdr-icon        — внешняя обёртка: подъём на 3px при hover/focus-visible;
//   .hdr-icon-inner  — внутренняя: анимация успешного действия (пульс сердца,
//                      столбики, проседание корзины, кивок кабинета) + декор.
// Пока идёт действие, внешняя обёртка помечена data-acting — CSS отключает
// подъём (действие приоритетнее наведения). Сами keyframes — в globals.css,
// секция «Микроанимации иконок шапки».
//
// Перезапуск при быстрых повторах — сменой key внутренней обёртки: новый узел
// начинает анимацию с нуля, а таймер снятия data-acting один и перевзводится.
// На маунте seq = 0 → ничего не играет при первой загрузке, восстановлении
// сохранённого списка и обычном перерендере: запуск только от события шины
// lib/action-feedback, которое издают реальные успешные добавления.
//
// Рисунок, размер и толщина линий — те же lucide-иконки, что и раньше. Сравнение
// нарисовано inline: столбики должны двигаться поодиночке, а lucide отдаёт
// монолитный svg. Path'ы и атрибуты повторяют lucide `chart-column` 1:1.

import { Heart, ShoppingCart, UserRound } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { subscribeActionSuccess, type ActionKind } from "@/lib/action-feedback";
import { cn } from "@/lib/utils";

// Длительности совпадают с animation-duration в globals.css (+ запас на задержки
// столбиков). По ним снимается data-acting; на animationend не полагаемся —
// при prefers-reduced-motion анимации нет, и hover остался бы заблокирован.
export const ACTION_DURATION_MS: Record<ActionKind | "account", number> = {
  wishlist: 650,
  compare: 650,
  cart: 700,
  account: 500,
};

export type Pulse = {
  /** Сколько раз действие запускалось; 0 — ни разу (ничего не играем). */
  seq: number;
  /** Действие идёт прямо сейчас. */
  active: boolean;
  /** Запустить (перезапустить) действие. */
  fire: () => void;
};

/** Одноразовый импульс с перевзводимым таймером; без накопления таймеров. */
export function usePulse(durationMs: number): Pulse {
  const [seq, setSeq] = useState(0);
  const [active, setActive] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fire = useCallback(() => {
    setSeq((current) => current + 1);
    setActive(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      setActive(false);
    }, durationMs);
  }, [durationMs]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return { seq, active, fire };
}

/** Импульс, привязанный к событиям шины «товар успешно добавлен». */
function useActionPulse(kind: ActionKind): Pulse {
  const pulse = usePulse(ACTION_DURATION_MS[kind]);
  const { fire } = pulse;
  useEffect(
    () =>
      subscribeActionSuccess((event) => {
        if (event === kind) fire();
      }),
    [kind, fire],
  );
  return pulse;
}

function Shell({
  pulse,
  kind,
  children,
}: {
  pulse: Pulse;
  kind: ActionKind | "account";
  children: React.ReactNode;
}) {
  const acting = pulse.active || undefined;
  return (
    <span className="hdr-icon" data-acting={acting}>
      <span
        key={pulse.seq}
        className={cn("hdr-icon-inner", `hdr-icon--${kind}`)}
        data-acting={acting}
      >
        {children}
      </span>
    </span>
  );
}

type IconProps = { className?: string };

export function WishlistActionIcon({ className }: IconProps) {
  const pulse = useActionPulse("wishlist");
  return (
    <Shell pulse={pulse} kind="wishlist">
      <Heart className={cn("hdr-heart", className)} aria-hidden />
      {/* Расходящееся кольцо: только декор, клики не ловит, в покое невидимо. */}
      <span className="hdr-ring" aria-hidden />
    </Shell>
  );
}

// lucide 1.21 `chart-column` (BarChart3): ось + три столбика, низ каждого на y=17.
const COMPARE_AXIS = "M3 3v16a2 2 0 0 0 2 2h16";
export const COMPARE_BARS = ["M18 17V9", "M13 17V5", "M8 17v-3"] as const;

export function CompareActionIcon({ className }: IconProps) {
  const pulse = useActionPulse("compare");
  return (
    <Shell pulse={pulse} kind="compare">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={24}
        height={24}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={cn("lucide lucide-chart-column", className)}
        aria-hidden="true"
      >
        <path d={COMPARE_AXIS} />
        {COMPARE_BARS.map((d) => (
          <path key={d} d={d} className="hdr-bar" />
        ))}
      </svg>
    </Shell>
  );
}

export function CartActionIcon({ className }: IconProps) {
  const pulse = useActionPulse("cart");
  return (
    <Shell pulse={pulse} kind="cart">
      <ShoppingCart className={cn("hdr-cart", className)} aria-hidden />
      {/* Квадратик-покупка, падающий в корзину: декор, в покое невидим. */}
      <span className="hdr-drop" aria-hidden />
    </Shell>
  );
}

/**
 * Кабинет: запускается не шиной, а активацией ссылки — владелец импульса
 * (Header, MobileBottomNav) вешает `pulse.fire` на onClick без preventDefault,
 * переход не ждёт анимацию.
 */
export function AccountActionIcon({ className, pulse }: IconProps & { pulse: Pulse }) {
  return (
    <Shell pulse={pulse} kind="account">
      <UserRound className={cn("hdr-wave", className)} aria-hidden />
    </Shell>
  );
}
