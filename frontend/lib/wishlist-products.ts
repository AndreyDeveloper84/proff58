// Карточки товаров избранного — через свой BFF-роут
// (app/api/account/wishlist/products).
//
// Избранное на бэкенде хранит только связь «пользователь ↔ товар», и раньше
// страница показывала то, что отдавал этот эндпоинт: название, ссылку и серую
// заглушку вместо фотографии — без цены и наличия. Данные для карточки живут в
// каталоге, поэтому берём их оттуда — тем же адаптером, что и вся выдача.
//
// Товар, снятый с публикации, API просто не вернёт: избранное не должно быть
// лазейкой к скрытым позициям.

import { apiFetch } from "@/lib/api";
import type { Product } from "@/lib/types";

export async function fetchWishlistProducts(ids: number[]): Promise<Product[]> {
  if (ids.length === 0) return [];
  const { products } = await apiFetch<{ products: Product[] }>(
    `/api/account/wishlist/products?ids=${ids.join(",")}`,
    { method: "GET" },
  );
  // Порядок задаёт избранное, а не выдача каталога: человек ждёт свой список.
  const byId = new Map(products.map((product) => [product.id, product]));
  return ids.map((id) => byId.get(id)).filter((product): product is Product => product != null);
}
