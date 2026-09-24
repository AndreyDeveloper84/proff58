// BFF: POST /api/account/oauth/{provider}/link → Django. Старт привязки из ЛК:
// Django кладёт state в сессию и отдаёт {url} провайдера.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";
import { isOAuthProvider } from "@/lib/oauth";

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ provider: string }> },
): Promise<Response> {
  const { provider } = await ctx.params;
  // Провайдер уходит в путь Django — только из белого списка, без «../» и прочего.
  if (!isOAuthProvider(provider)) {
    return Response.json({ detail: "Не найдено." }, { status: 404 });
  }
  return proxyToDjango(request, `/api/account/oauth/${provider}/link/`, {
    method: "POST",
    body: "{}",
  });
}
