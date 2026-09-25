// BFF: POST/DELETE /api/cart/promo → Django (#571). Мутации требуют CSRF — решает BFF.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/cart/promo/", { method: "POST", body });
}

export async function DELETE(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/cart/promo/", { method: "DELETE" });
}
