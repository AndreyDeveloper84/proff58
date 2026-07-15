// BFF: POST /api/account/max/link/ → Django (#492). Старт привязки MAX из ЛК.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/max/link/", { method: "POST", body: "{}" });
}
