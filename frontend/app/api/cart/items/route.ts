// BFF: POST /api/cart/items/ → Django (#246). Тело {product_id, quantity>=1}.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/cart/items/", { method: "POST", body });
}
