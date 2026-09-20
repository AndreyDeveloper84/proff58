"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
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
  const [product, setProduct] = useState<Product | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  const open = useCallback((next: Product, trigger?: HTMLElement | null) => {
    triggerRef.current = trigger ?? null;
    setProduct(next);
  }, []);

  const close = useCallback(() => {
    setProduct(null);
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
      {product && <QuickViewDialog key={product.id} product={product} onClose={close} />}
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
