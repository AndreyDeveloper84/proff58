// BFF: POST /api/account/notifications/read-all → Django (#515).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/notifications/read-all/", { method: "POST" });
}
