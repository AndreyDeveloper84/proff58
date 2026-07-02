// BFF: POST /api/account/otp-login/ → Django (#434/M-11).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/otp-login/", { method: "POST", body });
}
