// BFF: GET/POST/DELETE /api/account/wishlist/ → Django (#434/M-11). Мутации требуют CSRF.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/wishlist/", { method: "GET" });
}

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/wishlist/", { method: "POST", body });
}

export async function DELETE(request: NextRequest): Promise<Response> {
  // Пустая строка → undefined: иначе в Django уйдёт Content-Type: application/json
  // с пустым телом, и request.data упадёт с ParseError (400 «JSON parse error»).
  const body = await request.text();
  return proxyToDjango(request, "/api/account/wishlist/", {
    method: "DELETE",
    body: body || undefined,
  });
}
