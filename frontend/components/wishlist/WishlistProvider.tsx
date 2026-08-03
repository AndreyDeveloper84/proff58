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
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

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
  /** По этому товару сейчас идёт запрос — повторный клик игнорируем. */
  isPending: (productId: number) => boolean;
};

const EMPTY: ReadonlySet<number> = new Set();

// Вне провайдера (юнит-тест карточки, изолированный рендер) сердечко просто
// ничего не сохраняет — падать из-за отсутствия контекста ему незачем.
const WishlistContext = createContext<WishlistContextValue>({
  ids: EMPTY,
  loaded: false,
  has: () => false,
  toggle: () => {},
  isPending: () => false,
});

export function WishlistProvider({ children }: { children: React.ReactNode }) {
  const authState = useAuthState();
  const router = useRouter();
  const pathname = usePathname();
  // null — список ещё не пришёл. Гостю его и не ждать, поэтому «загружено» и
  // «что в избранном» выводятся, а не хранятся отдельным состоянием: иначе
  // пришлось бы синхронизировать их из effect'а на каждый вход-выход.
  const [storedIds, setStoredIds] = useState<ReadonlySet<number> | null>(null);
  const [pendingIds, setPendingIds] = useState<ReadonlySet<number>>(EMPTY);
  // Клики, сделанные до прихода списка: ответ сервера сформирован раньше их и
  // не должен их затирать. id → «лежит ли товар в избранном после клика».
  const localOverrides = useRef(new Map<number, boolean>());

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
      if (!active || items === "error") return;
      const merged = new Set(items.map((item) => item.product_id));
      for (const [productId, inList] of localOverrides.current) {
        if (inList) merged.add(productId);
        else merged.delete(productId);
      }
      setStoredIds(merged);
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
      // Блокируем только повторный клик по этому же товару: сердечки соседних
      // карточек должны работать, пока идёт чужой запрос.
      if (pendingIds.has(productId)) return;

      const willAdd = !ids.has(productId);
      // Функциональные обновления, а не снимок из замыкания: параллельные
      // клики по разным товарам иначе затирали бы друг друга.
      const applyLocally = (add: boolean) => {
        localOverrides.current.set(productId, add);
        setStoredIds((current) => {
          const next = new Set(current ?? EMPTY);
          if (add) next.add(productId);
          else next.delete(productId);
          return next;
        });
      };

      // Оптимистично: сердечко откликается сразу, откат — только если сервер отказал.
      applyLocally(willAdd);
      setPendingIds((current) => new Set(current).add(productId));

      const request = willAdd ? addWishlistItem(productId) : removeWishlistItem(productId);
      request
        .catch((error: unknown) => {
          applyLocally(!willAdd);
          // Сессия истекла, пока человек ходил по каталогу, — это не сбой, а вход.
          if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
            toLogin();
          }
        })
        .finally(() =>
          setPendingIds((current) => {
            const next = new Set(current);
            next.delete(productId);
            return next;
          }),
        );
    },
    [ids, isGuest, pendingIds, toLogin],
  );

  const value = useMemo<WishlistContextValue>(
    () => ({
      ids,
      loaded,
      has: (productId: number) => ids.has(productId),
      toggle,
      isPending: (productId: number) => pendingIds.has(productId),
    }),
    [ids, loaded, toggle, pendingIds],
  );

  return <WishlistContext.Provider value={value}>{children}</WishlistContext.Provider>;
}

export function useWishlist(): WishlistContextValue {
  return useContext(WishlistContext);
}
