// BFF: POST /api/account/max/unlink/ → Django (#492). Отключить привязку MAX.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  return proxyToDjango(request, "/api/account/max/unlink/", { method: "POST", body: "{}" });
}
