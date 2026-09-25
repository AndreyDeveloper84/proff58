import type { MetadataRoute } from "next";

import { siteOrigin, sitemapApiBase, sitemapEntries, type SitemapProductRow } from "@/lib/seo";
import { ssrHeaders } from "@/lib/ssr";

// PF-SH-RELEASE-01: sitemap.xml — только карточки, открытые для индексации (allowlist
// release-gate ∩ видимые; backend /api/catalog/seo/sitemap-products/). Остальной каталог
// noindex и в sitemap не попадает. Без INTERNAL_API_BASE_URL — пустой sitemap, но только
// вне production (см. sitemapApiBase).
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = sitemapApiBase(process.env);
  if (!base) return [];
  const res = await fetch(`${base}/api/catalog/seo/sitemap-products/`, {
    cache: "no-store",
    headers: ssrHeaders(),
    signal: AbortSignal.timeout(8000),
  });
  // Ошибку API не маскируем пустым sitemap: краулер повторит 5xx, а пустой список
  // прочитал бы как «товаров больше нет».
  if (!res.ok) throw new Error(`sitemap-products ${res.status}`);
  return sitemapEntries((await res.json()) as SitemapProductRow[], siteOrigin());
}
