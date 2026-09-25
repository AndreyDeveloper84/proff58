// BFF: GET /api/orders/{number}/guest?t=… → Django. Свежий заказ гостю по токену.
//
// Нужен странице «Спасибо»: снимок из sessionStorage показывает состояние на
// момент оформления, а после возврата из кассы важно именно текущее — оплачен
// заказ или ещё ждёт подтверждения.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ number: string }> },
): Promise<Response> {
  const { number } = await ctx.params;
  const token = request.nextUrl.searchParams.get("t") ?? "";
  const query = token ? `?t=${encodeURIComponent(token)}` : "";
  return proxyToDjango(request, `/api/orders/${encodeURIComponent(number)}/guest/${query}`, {
    method: "GET",
  });
}
