// BFF: GET /api/account/invoices → Django (#560). Owner-only список счетов B2B.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  const qs = request.nextUrl.search;
  return proxyToDjango(request, `/api/account/invoices/${qs}`, { method: "GET" });
}
