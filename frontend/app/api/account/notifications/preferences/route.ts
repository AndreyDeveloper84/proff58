// BFF: GET/PATCH /api/account/notifications/preferences → Django (#515/#519).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/notifications/preferences/", { method: "GET" });
}

export async function PATCH(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/notifications/preferences/", {
    method: "PATCH",
    body,
  });
}
