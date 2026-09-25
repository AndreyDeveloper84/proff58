// BFF: POST /api/account/register/ → Django (#434/M-11).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/account/register/", { method: "POST", body });
}
