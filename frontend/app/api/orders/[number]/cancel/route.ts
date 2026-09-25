// BFF: POST /api/orders/{number}/cancel/ → Django. Отмена заказа покупателем.
// Мутация вошедшего пользователя, поэтому обязательно через BFF: он добавляет
// самосогласованный CSRF, без которого Django ответил бы 403.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ number: string }> },
): Promise<Response> {
  const { number } = await ctx.params;
  return proxyToDjango(request, `/api/orders/${encodeURIComponent(number)}/cancel/`, {
    method: "POST",
  });
}
