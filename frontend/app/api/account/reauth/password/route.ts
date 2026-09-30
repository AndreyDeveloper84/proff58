// BFF: POST /api/account/reauth/password/ → Django (DRF-2497). Подтверждение
// личности паролем; сервер меняет ключ сессии — Set-Cookie отдаёт proxyToDjango.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/reauth/password/", {
    method: "POST",
    body: body || "{}",
  });
}
