"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Cart } from "@/lib/types";
import {
  addToCart as apiAdd,
  applyPromoCode as apiApplyPromo,
  getCart,
  removeItem as apiRemove,
  removePromoCode as apiRemovePromo,
  updateItem as apiUpdate,
} from "@/lib/cart";

type CartContextValue = {
  cart: Cart | null;
  // Загрузка стартового снимка (getCart на маунте). Мутации трекаются локально у вызова.
  loading: boolean;
  // Суммарное число единиц во всех строках — для бейджа в Header.
  count: number;
  // Итоговая сумма корзины числом (Cart.total приходит строкой).
  total: number;
  add: (productId: number, quantity?: number) => Promise<Cart>;
  update: (itemId: number, quantity: number) => Promise<Cart>;
  remove: (itemId: number) => Promise<Cart>;
  // #571: промокод. Ошибку 400 (невалидный код) пробрасываем вызову — поле покажет detail.
  applyPromo: (code: string) => Promise<Cart>;
  removePromo: () => Promise<Cart>;
  refresh: () => Promise<void>;
};

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);

  // «Поколение» запроса: корзина-мутации не сериализованы (add зовётся из карточек без общей
  // блокировки), поэтому применяем снимок, только если запрос — последний из стартовавших.
  // Иначе поздний ответ старого запроса перезатёр бы более свежий (UI-рассинхрон счётчика).
  const seqRef = useRef(0);
  const applyIfLatest = useCallback((seq: number, next: Cart) => {
    if (seqRef.current === seq) setCart(next);
    return next;
  }, []);

  const refresh = useCallback(async () => {
    const seq = ++seqRef.current;
    try {
      applyIfLatest(seq, await getCart());
    } catch {
      // Корзина не загрузилась — оставляем null (Header покажет пустой счётчик).
      if (seqRef.current === seq) setCart(null);
    }
  }, [applyIfLatest]);

  useEffect(() => {
    const seq = ++seqRef.current;
    getCart()
      .then((c) => {
        if (seqRef.current === seq) setCart(c);
      })
      .catch(() => {
        // Гость без сессии/сбой — корзина пустая; не блокируем витрину.
      })
      .finally(() => {
        setLoading(false);
      });
    // seqRef защищает от перезаписи поздним стартовым ответом, отдельный active-флаг не нужен.
  }, []);

  // Мутации возвращают полный снимок: применяем к состоянию (если запрос последний) и
  // всегда пробрасываем ответ/ошибку вызову (кнопкам — для состояний «Добавлено»/ошибка).
  const add = useCallback(
    async (productId: number, quantity = 1) => {
      const seq = ++seqRef.current;
      return applyIfLatest(seq, await apiAdd(productId, quantity));
    },
    [applyIfLatest],
  );

  const update = useCallback(
    async (itemId: number, quantity: number) => {
      const seq = ++seqRef.current;
      return applyIfLatest(seq, await apiUpdate(itemId, quantity));
    },
    [applyIfLatest],
  );

  const remove = useCallback(
    async (itemId: number) => {
      const seq = ++seqRef.current;
      return applyIfLatest(seq, await apiRemove(itemId));
    },
    [applyIfLatest],
  );

  const applyPromo = useCallback(
    async (code: string) => {
      const seq = ++seqRef.current;
      return applyIfLatest(seq, await apiApplyPromo(code));
    },
    [applyIfLatest],
  );

  const removePromo = useCallback(async () => {
    const seq = ++seqRef.current;
    return applyIfLatest(seq, await apiRemovePromo());
  }, [applyIfLatest]);

  const value = useMemo<CartContextValue>(() => {
    const lines = cart?.lines ?? [];
    return {
      cart,
      loading,
      count: lines.reduce((sum, l) => sum + l.quantity, 0),
      total: cart ? Number(cart.total) || 0 : 0,
      add,
      update,
      remove,
      applyPromo,
      removePromo,
      refresh,
    };
  }, [cart, loading, add, update, remove, applyPromo, removePromo, refresh]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) {
    throw new Error("useCart должен использоваться внутри <CartProvider>");
  }
  return ctx;
}
