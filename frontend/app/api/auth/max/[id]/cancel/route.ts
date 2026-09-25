// BFF: POST /api/auth/max/{id}/cancel/ → Django (#492). Отмена попытки пользователем.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(
  request: NextRequest,
  ctx: RouteContext<"/api/auth/max/[id]/cancel">,
): Promise<Response> {
  const { id } = await ctx.params;
  return proxyToDjango(request, `/api/auth/max/${encodeURIComponent(id)}/cancel/`, {
    method: "POST",
    body: "{}",
  });
}
