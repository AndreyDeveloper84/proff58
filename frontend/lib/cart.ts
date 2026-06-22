// API-клиент корзины — клиентские вызовы (из браузера) через /api/cart/.
// Корзина привязана к сессии (session_key cookie) — работает для гостей и
// аутентифицированных. Все мутации возвращают полный снимок корзины.

export type CartLine = {
  id: number;
  product_id: number;
  name: string;
  slug: string;
  quantity: number;
  price_final: string | null;
  price_base: string | null;
  discount: string | null;
  price_type: string;
  currency: string;
  line_total: string | null;
};

export type Cart = {
  id: number;
  status: string;
  lines: CartLine[];
  total: string;
  currency: string;
};

const API_BASE = "/api";

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Cart API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** Получить текущую корзину. */
export function getCart(): Promise<Cart> {
  return apiFetch<Cart>("/cart/");
}

/** Добавить товар в корзину. */
export function addToCart(productId: number, quantity = 1): Promise<Cart> {
  return apiFetch<Cart>("/cart/items/", {
    method: "POST",
    body: JSON.stringify({ product_id: productId, quantity }),
  });
}

/** Изменить количество позиции. */
export function updateItem(itemId: number, quantity: number): Promise<Cart> {
  return apiFetch<Cart>(`/cart/items/${itemId}/`, {
    method: "PATCH",
    body: JSON.stringify({ quantity }),
  });
}

/** Удалить позицию из корзины. */
export function removeItem(itemId: number): Promise<Cart> {
  return apiFetch<Cart>(`/cart/items/${itemId}/`, {
    method: "DELETE",
  });
}
