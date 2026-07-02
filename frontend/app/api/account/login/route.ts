// BFF: POST /api/account/login/ → Django (#434/M-11). CSRF/сессия — в proxyToDjango.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/login/", { method: "POST", body });
}
