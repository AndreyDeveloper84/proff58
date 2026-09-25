// BFF: GET /api/account/max/status/ → Django (#492). Привязан ли MAX у пользователя.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/max/status/", { method: "GET" });
}
