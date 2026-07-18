// BFF: GET /api/account/notifications/unread-count → Django (#515).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function GET(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/notifications/unread-count/", { method: "GET" });
}
