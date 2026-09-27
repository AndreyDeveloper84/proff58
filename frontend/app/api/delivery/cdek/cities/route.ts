// BFF: GET /api/delivery/cdek/cities?q= → Django (DRF-2491): подсказки городов СДЭК.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const qs = request.nextUrl.search;
  return proxyToDjango(request, `/api/delivery/cdek/cities/${qs}`, { method: "GET" });
}
