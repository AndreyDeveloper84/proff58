// BFF: POST /api/account/change-phone/ → Django. Новый телефон подтверждается паролем.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/change-phone/", {
    method: "POST",
    body,
  });
}
