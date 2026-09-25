// BFF: GET/POST /api/account/reviews → Django (#573). Мутация требует CSRF — решает BFF.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const qs = request.nextUrl.search;
  return proxyToDjango(request, `/api/account/reviews/${qs}`, { method: "GET" });
}

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/reviews/", { method: "POST", body });
}
