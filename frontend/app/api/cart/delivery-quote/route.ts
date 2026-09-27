// BFF: POST /api/cart/delivery-quote → Django (DRF-2491). Расчёт доставки СДЭК по
// серверной корзине; мутация вошедшего покупателя требует CSRF — решает BFF.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/cart/delivery-quote/", { method: "POST", body });
}
