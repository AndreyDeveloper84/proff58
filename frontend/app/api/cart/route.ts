// BFF: GET /api/cart/ → Django GET /api/cart/ (#246). Корзина гостя по session_key —
// сессия заводится Django и пробрасывается клиенту через Set-Cookie прокси.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/cart/", { method: "GET" });
}
