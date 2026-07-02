// BFF: GET/POST /api/orders/ → Django (#246, #434/M-11). POST — оформление заказа из
// активной корзины (цена считается на сервере); GET — список заказов пользователя.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/orders/", { method: "GET" });
}

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/orders/", { method: "POST", body });
}
