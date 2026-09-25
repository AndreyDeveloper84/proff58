// BFF: POST /api/orders/{number}/max-track/start/ → Django (#520). access_token —
// в теле запроса (не в query), гостевой токен заказа держим подальше от URL.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(
  request: NextRequest,
  ctx: RouteContext<"/api/orders/[number]/max-track/start">,
): Promise<Response> {
  const { number } = await ctx.params;
  const body = await request.text();
  return proxyToDjango(request, `/api/orders/${encodeURIComponent(number)}/max-track/start/`, {
    method: "POST",
    body,
  });
}
