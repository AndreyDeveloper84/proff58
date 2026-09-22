// BFF: POST /api/account/password-reset/confirm/ → Django (DRF-2298).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/password-reset/confirm/", {
    method: "POST",
    body,
  });
}
