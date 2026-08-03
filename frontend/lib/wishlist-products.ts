// Карточки товаров избранного — из публичного API каталога, одним запросом.
//
// Избранное на бэкенде хранит только связь «пользователь ↔ товар», и раньше
// страница показывала то, что отдавал этот эндпоинт: название, ссылку и серую
// заглушку вместо фотографии — без цены и наличия. Данные для карточки живут в
// каталоге, поэтому берём их оттуда — тем же адаптером, что и вся выдача.
//
// Товар, снятый с публикации, API просто не вернёт: избранное не должно быть
// лазейкой к скрытым позициям.

import { apiFetch } from "@/lib/api";
import { apiProductToProduct, type ApiProduct } from "@/lib/adapters";
import type { Product } from "@/lib/types";

type ProductsPage = { results?: ApiProduct[] };

export async function fetchWishlistProducts(ids: number[]): Promise<Product[]> {
  if (ids.length === 0) return [];
  // limit, а не page_size: пагинация каталога — LimitOffsetPagination, и без
  // явного лимита ответ обрезался бы страницей по умолчанию (24 позиции).
  const params = new URLSearchParams({
    ids: ids.join(","),
    limit: String(ids.length),
  });
  const data = await apiFetch<ProductsPage | ApiProduct[]>(
    `/api/catalog/products/?${params.toString()}`,
    { method: "GET" },
  );
  const rows = Array.isArray(data) ? data : (data.results ?? []);
  const products = rows.map(apiProductToProduct);
  // Порядок задаёт избранное, а не выдача каталога: человек ждёт свой список.
  const byId = new Map(products.map((product) => [product.id, product]));
  return ids.map((id) => byId.get(id)).filter((product): product is Product => product != null);
}
