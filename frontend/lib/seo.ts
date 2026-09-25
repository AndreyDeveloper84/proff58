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

/**
 * Канонический origin сайта; читается в рантайме контейнера (SITE_URL), не на build.
 *
 * Единственный источник адреса для canonical, og:url, JSON-LD, robots и sitemap: раньше
 * первые три брали build-time NEXT_PUBLIC_SITE_URL и при смене домена разошлись бы с
 * robots и sitemap. Значение без схемы («proff58.ru») игнорируем: metadataBase строится
 * на каждой странице, и опечатка в .env роняла бы весь сайт, а не один robots.txt.
 *
 * Только сервер: в браузере SITE_URL нет, там всегда будет домен по умолчанию.
 */
export function siteOrigin(): string {
  for (const raw of [process.env.SITE_URL, process.env.NEXT_PUBLIC_SITE_URL]) {
    if (!raw) continue;
    try {
      const url = new URL(raw);
      if (url.protocol === "https:" || url.protocol === "http:") return raw.replace(/\/+$/, "");
    } catch {
      // не URL — пробуем следующий источник
    }
  }
  return DEFAULT_ORIGIN;
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

export type SitemapProductRow = { slug: string; updated_at: string | null };

export function sitemapEntries(rows: SitemapProductRow[], origin: string): MetadataRoute.Sitemap {
  return rows.map((r) => {
    const url = `${origin}/product/${encodeURIComponent(r.slug)}`;
    // Одна битая дата роняла весь sitemap.xml (Invalid Date → toISOString бросает), а
    // null превращался в 1970 год. Запись без lastModified честнее и краулеру не вредит.
    const modified = r.updated_at ? new Date(r.updated_at) : null;
    return modified && !Number.isNaN(modified.getTime()) ? { url, lastModified: modified } : { url };
  });
}

/**
 * Адрес API для sitemap; `null` — API не настроен, и sitemap пустой (сборка, локалка).
 *
 * В production пустой sitemap с кодом 200 краулер читает как «товаров больше нет» —
 * ровно то, от чего app/sitemap.ts защищается при сбое API. Поэтому там потерянная
 * переменная — ошибка (5xx, краулер повторит), а не тихий пустой список.
 */
export function sitemapApiBase(env: Record<string, string | undefined>): string | null {
  const base = env.INTERNAL_API_BASE_URL?.replace(/\/$/, "");
  if (base) return base;
  if (env.SEO_INDEXING === "production") {
    throw new Error("sitemap: INTERNAL_API_BASE_URL не задан при SEO_INDEXING=production");
  }
  return null;
}
