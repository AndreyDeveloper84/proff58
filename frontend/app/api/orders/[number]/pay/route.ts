// BFF: POST /api/orders/{number}/pay → Django /api/payments/orders/{number}/.
// Гостевой токен доступа идёт в ?t= — тем же контрактом, что у гостевого заказа.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ number: string }> },
): Promise<Response> {
  const { number } = await ctx.params;
  const token = request.nextUrl.searchParams.get("t") ?? "";
  const query = token ? `?t=${encodeURIComponent(token)}` : "";
  return proxyToDjango(request, `/api/payments/orders/${encodeURIComponent(number)}/${query}`, {
    method: "POST",
  });
}
