// BFF: GET /api/orders/max-track/{public_id}/status/ → Django (#520). Статус
// track_order-попытки — НЕ логинит (гость остаётся гостем), в отличие от
// /api/auth/max/{id}/status/.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(
  request: NextRequest,
  ctx: RouteContext<"/api/orders/max-track/[public_id]/status">,
): Promise<Response> {
  const { public_id } = await ctx.params;
  return proxyToDjango(request, `/api/orders/max-track/${encodeURIComponent(public_id)}/status/`, {
    method: "GET",
  });
}
