// BFF: POST /api/auth/max/{id}/confirm/ → Django (DRF-2740). Ввод кода из бота:
// единственный путь, которым попытка входа/привязки/подтверждения завершается.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(
  request: NextRequest,
  ctx: RouteContext<"/api/auth/max/[id]/confirm">,
): Promise<Response> {
  const { id } = await ctx.params;
  return proxyToDjango(request, `/api/auth/max/${encodeURIComponent(id)}/confirm/`, {
    method: "POST",
  });
}
