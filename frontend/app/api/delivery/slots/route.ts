// BFF: GET /api/delivery/slots → Django /api/delivery/slots/ (#569).
// Слоты нужны чекауту для выбора даты/времени курьерской доставки (B2C).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const qs = request.nextUrl.search;
  return proxyToDjango(request, `/api/delivery/slots/${qs}`, { method: "GET" });
}
