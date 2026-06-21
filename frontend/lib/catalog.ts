// Слой данных каталога — единственная точка интеграции.
// Режим API (env CATALOG_API_BASE задан, напр. http://web:8000 в compose) →
// реальные данные из БД через Django-каталог-API. Иначе — фикстура (локальная разработка).
// getListing(query) возвращает УЖЕ РАЗРЕШЁННЫЙ листинг: товары текущей страницы,
// фасеты со счётчиками, total — серверная фильтрация/пагинация.

import perforatory from "@/fixtures/listing.perforatory.json";
import { fetchListingFromApi } from "./adapters";
import { applyListing } from "./filtering";
import type { Listing, ListingQuery } from "./types";

const FIXTURES: Record<string, Listing> = {
  perforatory: perforatory as unknown as Listing,
};

const API_BASE = process.env.CATALOG_API_BASE;

export async function getListing(query: ListingQuery): Promise<Listing | null> {
  if (API_BASE) {
    try {
      return await fetchListingFromApi(API_BASE, query); // null → категории нет (notFound)
    } catch (e) {
      console.error("Каталог-API недоступен, fallback на фикстуру:", e);
    }
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
