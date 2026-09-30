// BFF: POST /api/account/max/reauth/ → Django (DRF-2497). Подтверждение личности
// привязанным MAX из кабинета.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/max/reauth/", { method: "POST", body: "{}" });
}
