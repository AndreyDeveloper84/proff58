// BFF: GET /api/catalog/compare?slugs=a,b,c → карточки товаров для таблицы сравнения.
//
// Список выбранного живёт в localStorage браузера, поэтому отрендерить страницу
// на сервере по URL нельзя — товары догружаются отсюда. Правило «браузер ходит
// только в same-origin route handlers» соблюдено: наружу в Django запрашивает
// уже сервер.
import type { NextRequest } from "next/server";

import { fetchProductFromApi } from "@/lib/adapters";
import { COMPARE_LIMIT } from "@/lib/constants";

export async function GET(request: NextRequest): Promise<Response> {
  const raw = request.nextUrl.searchParams.get("slugs") ?? "";
  const slugs = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    // Лимит применяем и здесь: параметр приходит из браузера, и по нему нельзя
    // заказать выгрузку сотни карточек одним запросом.
    .slice(0, COMPARE_LIMIT);

  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base || slugs.length === 0) {
    return Response.json({ products: [] });
  }

  // Параллельно: четыре независимых запроса ждать по очереди незачем. Товар мог
  // быть снят с публикации, пока лежал в списке, — такой просто выпадает из
  // ответа, страница покажет остальные.
  const loaded = await Promise.all(
    slugs.map((slug) => fetchProductFromApi(base.replace(/\/$/, ""), slug).catch(() => null)),
  );

  return Response.json({ products: loaded.filter((p) => p !== null) });
}
