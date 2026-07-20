// BFF: POST /api/account/delete/ → Django. Удаление аккаунта требует сессию и CSRF.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/delete/", { method: "POST" });
}
