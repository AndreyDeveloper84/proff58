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
  const body = await request.text();
  return proxyToDjango(request, "/api/account/wishlist/", { method: "DELETE", body });
}
