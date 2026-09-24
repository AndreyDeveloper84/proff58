// BFF: GET /api/account/oauth → Django /api/account/oauth/. Привязки VK ID / Яндекс ID
// текущего пользователя (только включённые провайдеры).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/oauth/", { method: "GET" });
}
