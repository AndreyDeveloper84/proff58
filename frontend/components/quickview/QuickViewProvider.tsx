"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import type { Product } from "@/lib/types";
import { QuickViewDialog } from "./QuickViewDialog";

// Быстрый просмотр товара поверх списка (UX-05). Провайдер один на приложение: окно
// рисуется вне карточек, поэтому список под ним не перестраивается — фильтры,
// сортировка и позиция прокрутки остаются как были.

type QuickViewApi = {
  /** Открыть окно. `trigger` — элемент, на который вернуть фокус после закрытия. */
  open: (product: Product, trigger?: HTMLElement | null) => void;
};

const QuickViewContext = createContext<QuickViewApi | null>(null);

export function QuickViewProvider({ children }: { children: React.ReactNode }) {
  // Окно привязано к странице, на которой его открыли. Провайдер стоит в корневом
  // layout и между маршрутами не размонтируется, поэтому без привязки окно переживало
  // переход: ссылка «Сообщить о поступлении» внутри него и системная «Назад» меняли
  // страницу под окном, а оно оставалось поверх с заблокированной прокруткой.
  const pathname = usePathname();
  const [view, setView] = useState<{ product: Product; pathname: string | null } | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Сброс прямо в рендере, а не в эффекте: иначе запись дожила бы до возврата на тот
  // же адрес, и окно всплыло бы само. Диалог при этом размонтируется и сам снимает
  // блокировку прокрутки; фокус не возвращаем — карточки на новой странице уже нет.
  if (view && view.pathname !== pathname) setView(null);

  const open = useCallback(
    (next: Product, trigger?: HTMLElement | null) => {
      triggerRef.current = trigger ?? null;
      setView({ product: next, pathname });
    },
    [pathname],
  );

  const close = useCallback(() => {
    setView(null);
    // Фокус — обратно на карточку, с которой открывали: клавиатурный пользователь
    // продолжает список с того же места. preventScroll — не дёргаем прокрутку.
    const trigger = triggerRef.current;
    triggerRef.current = null;
    if (trigger?.isConnected) trigger.focus({ preventScroll: true });
  }, []);

  const api = useMemo(() => ({ open }), [open]);

  return (
    <QuickViewContext.Provider value={api}>
      {children}
      {view && view.pathname === pathname && (
        <QuickViewDialog key={view.product.id} product={view.product} onClose={close} />
      )}
    </QuickViewContext.Provider>
  );
}

/**
 * `null`, если провайдера нет. Карточка товара живёт и вне приложения (тесты,
 * демо-страницы) — там клик по ней остаётся обычным переходом по ссылке.
 */
export function useQuickView(): QuickViewApi | null {
  return useContext(QuickViewContext);
}
