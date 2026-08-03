// BFF: GET /api/catalog/wishlist?ids=1,2,3 → карточки товаров избранного.
//
// Избранное на бэкенде хранит только связь «пользователь ↔ товар», а данные
// карточки живут в каталоге. Правило «браузер ходит только в same-origin route
// handlers» соблюдено: наружу в Django запрашивает уже сервер — тот же приём,
// что у сравнения (app/api/catalog/compare).
import type { NextRequest } from "next/server";

import { fetchProductsByIdsFromApi } from "@/lib/adapters";

// Потолок совпадает с MAX_IDS_FILTER в apps/catalog/filters.py: параметр
// приходит из браузера, и по нему нельзя заказать выгрузку каталога.
const MAX_IDS = 200;

export async function GET(request: NextRequest): Promise<Response> {
  const ids = (request.nextUrl.searchParams.get("ids") ?? "")
    .split(",")
    .map((token) => Number(token.trim()))
    .filter((id) => Number.isInteger(id) && id > 0)
    .slice(0, MAX_IDS);

  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base || ids.length === 0) return Response.json({ products: [] });

  try {
    return Response.json({ products: await fetchProductsByIdsFromApi(base, ids) });
  } catch {
    // Сбой каталога — это не «избранное пусто»: страница обязана отличать одно
    // от другого, поэтому отвечаем ошибкой, а не пустым списком.
    return Response.json({ detail: "Каталог временно недоступен." }, { status: 502 });
  }
}
