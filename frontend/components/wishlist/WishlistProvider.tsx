"use client";

// Избранное покупателя — общее состояние на всю страницу.
//
// До этого сердечко на карточке было заглушкой: локальный useState, который
// перекрашивал иконку и забывал выбор при первом же переходе. Бэкенд избранного
// (`/api/account/wishlist/`) при этом существовал и работал — не хватало только
// провода между ним и карточкой.
//
// Два источника, по состоянию входа:
//   гость   — localStorage (lib/wishlist-storage), как список сравнения;
//   вошёл   — сервер, поэтому избранное доступно с любого устройства.
//
// При входе гостевой список ПЕРЕЕЗЖАЕТ в аккаунт и чистится. Без этого шага
// гостевое избранное было бы ловушкой: человек копил его месяцами, завёл
// аккаунт — и всё пропало. Перенос живёт здесь, а не в форме входа: так он
// покрывает сразу все способы (пароль, MAX, регистрация) и ни один не забудется.
//
// Состояние держим в одном месте: одна и та же позиция встречается в выдаче, в
// каруселях и в самом избранном, и все сердечки обязаны показывать одно и то же.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { useAuthState } from "@/components/auth/AuthStateProvider";
import { ApiError } from "@/lib/api";
import {
  addWishlistItem,
  addWishlistItems,
  getWishlist,
  removeWishlistItem,
} from "@/lib/auth";
import {
  clearGuestWishlist,
  readGuestWishlist,
  subscribeGuestWishlist,
  toggleGuestWishlist,
  WISHLIST_GUEST_LIMIT,
} from "@/lib/wishlist-storage";

type WishlistContextValue = {
  /** Идентификаторы товаров в избранном. */
  ids: ReadonlySet<number>;
  /** Список уже загружен (или загружать нечего — гость). */
  loaded: boolean;
  has: (productId: number) => boolean;
  /** Добавить/убрать. Вход не требуется — гостю список сохраняется в браузере. */
  toggle: (productId: number) => void;
  /** По этому товару сейчас идёт запрос — повторный клик игнорируем. */
  isPending: (productId: number) => boolean;
  /** Гостевой список: живёт только в этом браузере (для подсказки на странице). */
  isGuest: boolean;
  /** Упёрлись в лимит гостевого списка — последний товар не сохранён. */
  limitReached: boolean;
};

const EMPTY: ReadonlySet<number> = new Set();
const EMPTY_ARRAY: number[] = [];

// Вне провайдера (юнит-тест карточки, изолированный рендер) сердечко просто
// ничего не сохраняет — падать из-за отсутствия контекста ему незачем.
const WishlistContext = createContext<WishlistContextValue>({
  ids: EMPTY,
  loaded: false,
  has: () => false,
  toggle: () => {},
  isPending: () => false,
  isGuest: false,
  limitReached: false,
});

export function WishlistProvider({ children }: { children: React.ReactNode }) {
  const authState = useAuthState();
  const isGuest = authState === "anonymous";

  // Гостевая часть — внешнее хранилище, читаем через useSyncExternalStore:
  // на сервере localStorage нет, и серверный снимок обязан быть пустым.
  const guestIds = useSyncExternalStore(
    subscribeGuestWishlist,
    readGuestWishlist,
    () => EMPTY_ARRAY,
  );

  // null — серверный список ещё не пришёл. Гостю его и не ждать, поэтому
  // «загружено» выводится, а не хранится отдельным состоянием.
  const [storedIds, setStoredIds] = useState<ReadonlySet<number> | null>(null);
  const [pendingIds, setPendingIds] = useState<ReadonlySet<number>>(EMPTY);
  const [limitReached, setLimitReached] = useState(false);
  // Клики, сделанные до прихода списка: ответ сервера собран раньше их и не
  // должен их затирать. id → «лежит ли товар в избранном после клика».
  const localOverrides = useRef(new Map<number, boolean>());

  const ids = useMemo<ReadonlySet<number>>(
    () => (isGuest ? new Set(guestIds) : (storedIds ?? EMPTY)),
    [isGuest, guestIds, storedIds],
  );
  const loaded = isGuest || storedIds !== null;

  useEffect(() => {
    if (isGuest) return;
    let active = true;
    // Вошёл — сначала переносим то, что накопилось в браузере, потом читаем
    // серверный список: иначе перенесённое не попало бы в выдачу до перезагрузки.
    const local = readGuestWishlist();
    const merge = local.length > 0 ? addWishlistItems(local).then(clearGuestWishlist) : null;

    Promise.resolve(merge)
      .catch(() => {
        // Перенос не удался — гостевой список НЕ чистим: попробуем на следующей
        // загрузке. Потерять сохранённое хуже, чем перенести дважды.
      })
      .then(() => getWishlist())
      .then((items) => {
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

  const toggle = useCallback(
    (productId: number) => {
      if (isGuest) {
        setLimitReached(!toggleGuestWishlist(productId));
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
          // Сессия истекла, пока человек ходил по каталогу: дальше он гость, и
          // список у него теперь браузерный — сохраняем клик туда, а не теряем.
          if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
            toggleGuestWishlist(productId);
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
    [ids, isGuest, pendingIds],
  );

  const value = useMemo<WishlistContextValue>(
    () => ({
      ids,
      loaded,
      has: (productId: number) => ids.has(productId),
      toggle,
      isPending: (productId: number) => pendingIds.has(productId),
      isGuest,
      limitReached: limitReached && ids.size >= WISHLIST_GUEST_LIMIT,
    }),
    [ids, loaded, toggle, pendingIds, isGuest, limitReached],
  );

  return <WishlistContext.Provider value={value}>{children}</WishlistContext.Provider>;
}

export function useWishlist(): WishlistContextValue {
  return useContext(WishlistContext);
}
