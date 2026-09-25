// BFF: POST /api/auth/max/start/ → Django (#492). Создать попытку входа/регистрации.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/auth/max/start/", { method: "POST", body: "{}" });
}
