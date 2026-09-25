// BFF: GET /api/auth/max/{id}/status/ → Django (#492). Опрос статуса попытки.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(
  request: NextRequest,
  ctx: RouteContext<"/api/auth/max/[id]/status">,
): Promise<Response> {
  const { id } = await ctx.params;
  return proxyToDjango(request, `/api/auth/max/${encodeURIComponent(id)}/status/`, {
    method: "GET",
  });
}
