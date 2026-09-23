// BFF: GET /api/search/quick?q= → Django SearchQuickView (быстрый поиск в шапке):
// до 6 карточек товаров и до 3 разделов. Браузер ходит только в same-origin route
// handlers Next; сессию пробрасываем (proxyToDjango), потому что цена в карточке
// зависит от пользователя. Путь Django — со слэшем, чтобы не ловить APPEND_SLASH-
// редирект на каждый запрос подсказок.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const q = request.nextUrl.searchParams.get("q") ?? "";
  return proxyToDjango(request, `/api/catalog/search/quick/?q=${encodeURIComponent(q)}`, {
    method: "GET",
  });
}
