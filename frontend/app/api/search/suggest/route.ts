// BFF: GET /api/search/suggest?q= → Django ProductSuggestView (#246, #52).
// Публичный read-only эндпоинт, но ходим через BFF тем же правилом «браузер → только
// same-origin route handlers Next». Сервер дописывает слэш к пути Django (его urlconf —
// со слэшем), чтобы не ловить APPEND_SLASH-редирект на каждый ввод символа.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const q = request.nextUrl.searchParams.get("q") ?? "";
  return proxyToDjango(
    request,
    `/api/catalog/search/suggest/?q=${encodeURIComponent(q)}`,
    { method: "GET" },
  );
}
