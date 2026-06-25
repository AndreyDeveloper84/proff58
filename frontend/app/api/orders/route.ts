// BFF: POST /api/orders/ → Django (#246). Оформление заказа из активной корзины;
// цена считается на сервере (тело — CreateOrderSerializer). Ответ — снимок заказа.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/orders/", { method: "POST", body });
}
