// BFF: GET /api/orders/{number}/invoice/ → Django. Возвращает HTML-счёт B2B-заказа.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ number: string }> },
): Promise<Response> {
  const { number } = await ctx.params;
  // Гостевой токен (?t=) обязан дойти до Django: без него счёт по ссылке из
  // письма отдавал 404 — заказ есть, реквизиты есть, а открыть документ нельзя.
  const token = request.nextUrl.searchParams.get("t") ?? "";
  const query = token ? `?t=${encodeURIComponent(token)}` : "";
  return proxyToDjango(request, `/api/orders/${encodeURIComponent(number)}/invoice/${query}`, {
    method: "GET",
  });
}
