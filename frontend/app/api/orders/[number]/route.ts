// BFF: GET /api/orders/{number}/ → Django. Доступен только владельцу заказа.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ number: string }> },
): Promise<Response> {
  const { number } = await ctx.params;
  return proxyToDjango(request, `/api/orders/${encodeURIComponent(number)}/`, {
    method: "GET",
  });
}
