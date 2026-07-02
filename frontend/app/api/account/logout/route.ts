// BFF: POST /api/account/logout/ → Django (#434/M-11). Требует CSRF (аутентифицирован).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/logout/", { method: "POST" });
}
