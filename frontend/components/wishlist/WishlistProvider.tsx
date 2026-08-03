"use client";

// Избранное покупателя — общее состояние на всю страницу.
//
// До этого сердечко на карточке было заглушкой: локальный useState, который
// перекрашивал иконку и забывал выбор при первом же переходе. Бэкенд избранного
// (`/api/account/wishlist/`) при этом существовал и работал — не хватало только
// провода между ним и карточкой.
//
// Состояние держим здесь, а не в каждой карточке: одна и та же позиция
// встречается в выдаче, в каруселях и в самом избранном, и все сердечки обязаны
// показывать одно и то же. Список идентификаторов забирается один раз за
// загрузку страницы, дальше — только точечные POST/DELETE.

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { useAuthState } from "@/components/auth/AuthStateProvider";
import { ApiError } from "@/lib/api";
import { addWishlistItem, getWishlist, loginHref, removeWishlistItem } from "@/lib/auth";

type WishlistContextValue = {
  /** Идентификаторы товаров в избранном. */
  ids: ReadonlySet<number>;
  /** Список уже загружен (или загружать нечего — гость). */
  loaded: boolean;
  has: (productId: number) => boolean;
  /** Добавить/убрать. Гостя уводит на форму входа с возвратом на эту же страницу. */
  toggle: (productId: number) => void;
  /** Товар, по которому сейчас идёт запрос (для блокировки повторного клика). */
  pendingId: number | null;
};

const EMPTY: ReadonlySet<number> = new Set();

// Вне провайдера (юнит-тест карточки, изолированный рендер) сердечко просто
// ничего не сохраняет — падать из-за отсутствия контекста ему незачем.
const WishlistContext = createContext<WishlistContextValue>({
  ids: EMPTY,
  loaded: false,
  has: () => false,
  toggle: () => {},
  pendingId: null,
});

export function WishlistProvider({ children }: { children: React.ReactNode }) {
  const authState = useAuthState();
  const router = useRouter();
  const pathname = usePathname();
  // null — список ещё не пришёл. Гостю его и не ждать, поэтому «загружено» и
  // «что в избранном» выводятся, а не хранятся отдельным состоянием: иначе
  // пришлось бы синхронизировать их из effect'а на каждый вход-выход.
  const [storedIds, setStoredIds] = useState<ReadonlySet<number> | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);

  const isGuest = authState === "anonymous";
  const ids = isGuest ? EMPTY : (storedIds ?? EMPTY);
  const loaded = isGuest || storedIds !== null;

  useEffect(() => {
    // Гостю избранного не полагается — запрос дал бы только 401.
    if (isGuest) return;
    let active = true;
    getWishlist().then((items) => {
      // "error" (в том числе истёкшая сессия) — не повод врать пустым списком:
      // оставляем незагруженным, сердечки будут неактивны до перезагрузки.
      if (active && items !== "error") {
        setStoredIds(new Set(items.map((item) => item.product_id)));
      }
    });
    return () => {
      active = false;
    };
  }, [isGuest]);

  const toLogin = useCallback(() => {
    router.push(loginHref(pathname));
  }, [router, pathname]);

  const toggle = useCallback(
    (productId: number) => {
      if (isGuest) {
        toLogin();
        return;
      }
      if (pendingId !== null) return;

      const willAdd = !ids.has(productId);
      const previous = ids;
      const next = new Set(previous);
      if (willAdd) next.add(productId);
      else next.delete(productId);
      // Оптимистично: сердечко откликается сразу, откат — только если сервер отказал.
      setStoredIds(next);
      setPendingId(productId);

      const request = willAdd ? addWishlistItem(productId) : removeWishlistItem(productId);
      request
        .catch((error: unknown) => {
          setStoredIds(previous);
          // Сессия истекла, пока человек ходил по каталогу, — это не сбой, а вход.
          if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
            toLogin();
          }
        })
        .finally(() => setPendingId(null));
    },
    [ids, isGuest, pendingId, toLogin],
  );

  const value = useMemo<WishlistContextValue>(
    () => ({
      ids,
      loaded,
      has: (productId: number) => ids.has(productId),
      toggle,
      pendingId,
    }),
    [ids, loaded, toggle, pendingId],
  );

  return <WishlistContext.Provider value={value}>{children}</WishlistContext.Provider>;
}

export function useWishlist(): WishlistContextValue {
  return useContext(WishlistContext);
}
