// BFF: GET /api/orders/{number}/invoice/ → Django. Возвращает PDF-счёт B2B-заказа
// на скачивание (?as=html — та же вёрстка страницей).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ number: string }> },
): Promise<Response> {
  const { number } = await ctx.params;
  // Гостевой токен (?t=) обязан дойти до Django: без него счёт по ссылке из
  // письма отдавал 404 — заказ есть, реквизиты есть, а открыть документ нельзя.
  const token = request.nextUrl.searchParams.get("t") ?? "";
  const params = new URLSearchParams();
  if (token) params.set("t", token);
  // ?as=html — та же вёрстка страницей (отладка; «format» занят DRF под выбор рендерера).
  // Всё остальное не пробрасываем.
  if (request.nextUrl.searchParams.get("as") === "html") params.set("as", "html");
  const query = params.size ? `?${params.toString()}` : "";
  return proxyToDjango(request, `/api/orders/${encodeURIComponent(number)}/invoice/${query}`, {
    method: "GET",
  });
}
