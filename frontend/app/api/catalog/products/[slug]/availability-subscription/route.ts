// BFF: GET/POST/DELETE /api/catalog/products/{slug}/availability-subscription →
// Django (#517/#519). Требует сессии (IsAuthenticated на бэке) — идёт через BFF,
// не публичным SSR-фетчем, как read-only каталог (lib/catalog.ts).
import type { NextRequest } from "next/server";
import { proxyToDjango } from "@/lib/bff";

function djangoPath(slug: string): string {
  return `/api/catalog/products/${encodeURIComponent(slug)}/availability-subscription/`;
}

export async function GET(
  request: NextRequest,
  ctx: RouteContext<"/api/catalog/products/[slug]/availability-subscription">,
): Promise<Response> {
  const { slug } = await ctx.params;
  return proxyToDjango(request, djangoPath(slug), { method: "GET" });
}

export async function POST(
  request: NextRequest,
  ctx: RouteContext<"/api/catalog/products/[slug]/availability-subscription">,
): Promise<Response> {
  const { slug } = await ctx.params;
  return proxyToDjango(request, djangoPath(slug), { method: "POST", body: "{}" });
}

export async function DELETE(
  request: NextRequest,
  ctx: RouteContext<"/api/catalog/products/[slug]/availability-subscription">,
): Promise<Response> {
  const { slug } = await ctx.params;
  return proxyToDjango(request, djangoPath(slug), { method: "DELETE" });
}
