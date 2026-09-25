// BFF: POST /api/account/notifications/{id}/read → Django (#515).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(
  request: NextRequest,
  ctx: RouteContext<"/api/account/notifications/[id]/read">,
): Promise<Response> {
  const { id } = await ctx.params;
  return proxyToDjango(request, `/api/account/notifications/${encodeURIComponent(id)}/read/`, {
    method: "POST",
  });
}
