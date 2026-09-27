// BFF: GET /api/delivery/cdek/points?city_code= → Django (DRF-2491): пункты выдачи СДЭК.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const qs = request.nextUrl.search;
  return proxyToDjango(request, `/api/delivery/cdek/points/${qs}`, { method: "GET" });
}
