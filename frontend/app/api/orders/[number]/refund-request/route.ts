// BFF: GET/POST /api/orders/{number}/refund-request → Django
// /api/payments/orders/{number}/refund-request/. Заявка покупателя на возврат
// денег: мутация вошедшего, поэтому только через BFF (CSRF добавляет он).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

type Ctx = { params: Promise<{ number: string }> };

function target(number: string) {
  return `/api/payments/orders/${encodeURIComponent(number)}/refund-request/`;
}

export async function GET(request: NextRequest, ctx: Ctx): Promise<Response> {
  const { number } = await ctx.params;
  return proxyToDjango(request, target(number), { method: "GET" });
}

export async function POST(request: NextRequest, ctx: Ctx): Promise<Response> {
  const { number } = await ctx.params;
  const body = await request.text();
  return proxyToDjango(request, target(number), {
    method: "POST",
    body: body || undefined,
  });
}
