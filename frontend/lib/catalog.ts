// Слой данных каталога — единственная точка интеграции.
// Режим API (env INTERNAL_API_BASE_URL, напр. http://web:8000 в compose) — реальные данные из БД
// через Django-каталог-API. Ошибки API НЕ маскируем фикстурой (пробрасываются → error.tsx);
// 404 категории → null → notFound() в page.tsx. Фикстура — ТОЛЬКО локально/dev или при
// NEXT_PUBLIC_USE_FIXTURES=true (не тихий fallback на staging).

import perforatory from "@/fixtures/listing.perforatory.json";
import {
  fetchListingFromApi,
  fetchProductFromApi,
  fetchSearchFromApi,
  fetchCategoryTreeFromApi,
  fetchBestsellersFromApi,
  type CategoryNode,
} from "./adapters";
import { HOME_CONTENT } from "./home-content";
import { applyListing } from "./filtering";
import type { Listing, ListingQuery, Product, ProductDetail } from "./types";

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

// Поиск товаров для SSR-страницы /search. Без API_BASE (фикстур поиска нет) → пустой список.
export async function searchProducts(q: string): Promise<Product[]> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchSearchFromApi(API_BASE, q);
  }
  return [];
}

// Карточка товара (PDP). Только режим API (фикстуры товара нет): без API_BASE или при
// FORCE_FIXTURES → null → notFound() в page.tsx. Ошибки fetch пробрасываются (→ error.tsx).
export async function getProduct(slug: string): Promise<ProductDetail | null> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchProductFromApi(API_BASE, slug);
  }
  return null;
}

export type { CategoryNode };

// Корневые категории (depth==1) для блока главной. Без API → пусто (блок скрыт).
export async function getCategoryTree(): Promise<CategoryNode[]> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchCategoryTreeFromApi(API_BASE);
  }
  return [];
}

// «Хиты продаж» для главной. Без API → пусто (блок скрыт).
export async function getBestsellers(limit = 8): Promise<Product[]> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchBestsellersFromApi(API_BASE, HOME_CONTENT.bestsellerSlugs, limit);
  }
  return [];
}
