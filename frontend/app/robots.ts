import type { MetadataRoute } from "next";
import { headers } from "next/headers";

import { robotsPolicy, siteOrigin } from "@/lib/seo";

// PF-SH-RELEASE-01: robots.txt по среде. Открыт только при SEO_INDEXING=production и
// запросе на каноническом хосте; иначе Disallow: / (политика — lib/seo.ts).
// headers() делает маршрут request-time: иначе Next закэшировал бы robots.txt на build,
// где переменных среды контейнера ещё нет.
export default async function robots(): Promise<MetadataRoute.Robots> {
  const host = (await headers()).get("host");
  return robotsPolicy({ indexing: process.env.SEO_INDEXING, host, origin: siteOrigin() });
}
