// BFF: GET /api/delivery/zones → Django /api/delivery/zones/ (#54, аудит №5).
// Зоны нужны чекауту для выбора delivery_zone — без неё сервер не считает доставку.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const qs = request.nextUrl.search;
  return proxyToDjango(request, `/api/delivery/zones/${qs}`, { method: "GET" });
}
