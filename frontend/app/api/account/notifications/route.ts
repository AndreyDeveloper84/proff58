// BFF: GET /api/account/notifications?limit=&offset= → Django (#515). История
// уведомлений, пагинация DRF LimitOffsetPagination — прокидываем query как есть.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const qs = request.nextUrl.searchParams.toString();
  return proxyToDjango(
    request,
    `/api/account/notifications/${qs ? `?${qs}` : ""}`,
    { method: "GET" },
  );
}
