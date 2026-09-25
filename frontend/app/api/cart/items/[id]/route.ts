// BFF: PATCH/DELETE /api/cart/items/{id}/ → Django (#246). PATCH тело {quantity>=1}.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function PATCH(
  request: NextRequest,
  ctx: RouteContext<"/api/cart/items/[id]">,
): Promise<Response> {
  const { id } = await ctx.params;
  const body = await request.text();
  return proxyToDjango(request, `/api/cart/items/${encodeURIComponent(id)}/`, {
    method: "PATCH",
    body,
  });
}

export async function DELETE(
  request: NextRequest,
  ctx: RouteContext<"/api/cart/items/[id]">,
): Promise<Response> {
  const { id } = await ctx.params;
  return proxyToDjango(request, `/api/cart/items/${encodeURIComponent(id)}/`, {
    method: "DELETE",
  });
}
