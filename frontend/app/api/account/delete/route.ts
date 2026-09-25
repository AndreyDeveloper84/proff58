// BFF: POST /api/account/delete/ → Django. Удаление аккаунта требует сессию и CSRF.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  // Тело — пароль для подтверждения (у пришедших из MAX его нет — тело пустое).
  const body = await request.text();
  return proxyToDjango(request, "/api/account/delete/", {
    method: "POST",
    body: body || undefined,
  });
}
