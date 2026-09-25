// BFF: GET/PATCH /api/account/me/ → Django (#434/M-11). PATCH требует CSRF.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/me/", { method: "GET" });
}

export async function PATCH(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/me/", { method: "PATCH", body });
}
