// Политика индексации витрины (PF-SH-RELEASE-01).
//
// Два независимых уровня:
// 1. robots.txt (app/robots.ts) — переключатель обхода для всей среды. Открыт ТОЛЬКО при
//    SEO_INDEXING=production и запросе на каноническом хосте (SITE_URL). Любая другая или
//    незаданная среда, чужой хост (dev., IP, localhost) → Disallow: /.
// 2. meta robots на странице — что можно индексировать. По умолчанию noindex, follow
//    (app/layout.tsx); index только у карточек товара из замороженного allowlist
//    (API отдаёт seo_indexable, backend: apps/catalog/seo_index.py). sitemap.xml —
//    ровно эти карточки.
// Откат открытия: SEO_INDEXING=off (или убрать) и перезапустить frontend.
import type { MetadataRoute } from "next";

const DEFAULT_ORIGIN = "https://proff58.ru";

/** Канонический origin сайта; читается в рантайме контейнера (SITE_URL), не на build. */
export function siteOrigin(): string {
  const raw = process.env.SITE_URL || process.env.NEXT_PUBLIC_SITE_URL || DEFAULT_ORIGIN;
  return raw.replace(/\/+$/, "");
}

const CLOSED: MetadataRoute.Robots = { rules: { userAgent: "*", disallow: "/" } };

export function robotsPolicy(args: {
  indexing: string | undefined;
  host: string | null;
  origin: string;
}): MetadataRoute.Robots {
  if (args.indexing !== "production") return CLOSED;
  const canonicalHost = new URL(args.origin).host;
  if (!args.host || args.host.toLowerCase() !== canonicalHost) return CLOSED;
  return {
    // /api/ — JSON, не страницы; /*? — фасетные и прочие параметрические варианты
    // (бесконечное пространство обхода; канонические URL карточек и разделов без query).
    rules: { userAgent: "*", allow: "/", disallow: ["/api/", "/*?"] },
    sitemap: `${args.origin}/sitemap.xml`,
  };
}

/** robots-метаданные карточки: index только для allowlist, ссылки обходятся всегда. */
export function productSeoMetadata(product: { name: string; slug: string; seoIndexable: boolean }) {
  return {
    // Суффикс «— Профессионал» дописывает шаблон title из app/layout.tsx.
    title: product.name,
    alternates: { canonical: `/product/${product.slug}` },
    robots: { index: product.seoIndexable, follow: true },
  };
}

export type SitemapProductRow = { slug: string; updated_at: string };

export function sitemapEntries(rows: SitemapProductRow[], origin: string): MetadataRoute.Sitemap {
  return rows.map((r) => ({
    url: `${origin}/product/${encodeURIComponent(r.slug)}`,
    lastModified: new Date(r.updated_at),
  }));
}
