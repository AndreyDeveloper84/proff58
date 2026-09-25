// BFF: GET /api/account/invoices/{number} → Django (#560). Детали счёта, владелец.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(
  request: NextRequest,
  ctx: RouteContext<"/api/account/invoices/[number]">,
): Promise<Response> {
  const { number } = await ctx.params;
  return proxyToDjango(request, `/api/account/invoices/${encodeURIComponent(number)}/`, {
    method: "GET",
  });
}
