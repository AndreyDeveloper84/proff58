// Обёртки корзины к same-origin BFF (#246). Все мутации возвращают полный снимок
// корзины (Django отдаёт корзину целиком), поэтому состояние всегда заменяется ответом.
import { apiFetch } from "./api";
import type { Cart } from "./types";

// Пути BFF — без хвостового слэша: Next (trailingSlash:false) иначе 308-редиректит,
// что ломает точечный nginx-роутинг в prod. Внутрь Django route handler ходит уже со слэшем.

/** Текущая корзина (GET → Django /api/cart/). Заводит сессию гостя при первом обращении. */
export function getCart(): Promise<Cart> {
  return apiFetch<Cart>("/api/cart");
}

/** Добавить товар (POST → Django /api/cart/items/). */
export function addToCart(productId: number, quantity = 1): Promise<Cart> {
  return apiFetch<Cart>("/api/cart/items", {
    method: "POST",
    body: JSON.stringify({ product_id: productId, quantity }),
  });
}

/** Изменить количество строки (PATCH → Django /api/cart/items/{id}/). */
export function updateItem(itemId: number, quantity: number): Promise<Cart> {
  return apiFetch<Cart>(`/api/cart/items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify({ quantity }),
  });
}

/** Удалить строку (DELETE → Django /api/cart/items/{id}/). */
export function removeItem(itemId: number): Promise<Cart> {
  return apiFetch<Cart>(`/api/cart/items/${itemId}`, { method: "DELETE" });
}

/** Применить промокод (POST → Django /api/cart/promo/). 400 с detail при невалидном (#571). */
export function applyPromoCode(code: string): Promise<Cart> {
  return apiFetch<Cart>("/api/cart/promo", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

/** Снять промокод с корзины (DELETE → Django /api/cart/promo/). */
export function removePromoCode(): Promise<Cart> {
  return apiFetch<Cart>("/api/cart/promo", { method: "DELETE" });
}
