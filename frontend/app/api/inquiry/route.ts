// BFF: POST /api/inquiry → Django /api/leads/inquiries/ (заявка с карточки товара).
// Тело валидируется на стороне Django (ProductInquirySerializer); здесь — тонкий прокси.
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  return proxyToDjango(request, "/api/leads/inquiries/", { method: "POST", body });
}
