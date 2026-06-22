// Слой данных каталога — единственная точка интеграции.
// Режим API (env INTERNAL_API_BASE_URL, напр. http://web:8000 в compose) — реальные данные из БД
// через Django-каталог-API. Ошибки API НЕ маскируем фикстурой (пробрасываются → error.tsx);
// 404 категории → null → notFound() в page.tsx. Фикстура — ТОЛЬКО локально/dev или при
// NEXT_PUBLIC_USE_FIXTURES=true (не тихий fallback на staging).

import perforatory from "@/fixtures/listing.perforatory.json";
import { fetchListingFromApi } from "./adapters";
import { applyListing } from "./filtering";
import type { Listing, ListingQuery } from "./types";

const FIXTURES: Record<string, Listing> = {
  perforatory: perforatory as unknown as Listing,
};

const API_BASE = process.env.INTERNAL_API_BASE_URL;
const FORCE_FIXTURES = process.env.NEXT_PUBLIC_USE_FIXTURES === "true";

export async function getListing(query: ListingQuery): Promise<Listing | null> {
  if (API_BASE && !FORCE_FIXTURES) {
    // Ошибки fetch пробрасываются (→ error.tsx); null (404 категории) → notFound() в page.tsx.
    return await fetchListingFromApi(API_BASE, query);
  }
  const base = FIXTURES[query.category];
  if (!base) return null;
  const res = applyListing(base, query);
  return {
    ...base,
    facets: res.facets,
    products: res.products,
    total: res.total,
    page: res.page,
    perPage: query.perPage,
  };
}

export function listingCategories(): string[] {
  return Object.keys(FIXTURES);
}
