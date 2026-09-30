// BFF: POST /api/account/oauth/{provider}/reauth → Django (DRF-2497). Подтверждение
// личности привязанным провайдером: Django кладёт state в сессию и отдаёт {url}.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";
import { isOAuthProvider } from "@/lib/oauth";

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ provider: string }> },
): Promise<Response> {
  const { provider } = await ctx.params;
  // Провайдер уходит в путь Django — только из белого списка.
  if (!isOAuthProvider(provider)) {
    return Response.json({ detail: "Не найдено." }, { status: 404 });
  }
  const body = await request.text();
  return proxyToDjango(request, `/api/account/oauth/${provider}/reauth/`, {
    method: "POST",
    body: body || "{}",
  });
}
