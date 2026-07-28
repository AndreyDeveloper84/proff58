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
  fetchCategoryProductsFromApi,
  fetchBestsellersFromApi,
  type CategoryNode,
} from "./adapters";
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

// Дерево категорий для индекса каталога. null — API недоступен («каталог временно
// недоступен»), [] — разделов нет. Без API_BASE/при фикстурах отдаём разделы, для
// которых есть фикстура листинга, — чтобы ссылки на локальной сборке не вели в 404.
export async function getCategoryTreeOrNull(): Promise<CategoryNode[] | null> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchCategoryTreeFromApi(API_BASE);
  }
  return Object.entries(FIXTURES).map(([slug, listing], index) => ({
    id: -(index + 1),
    name: listing.category.title,
    slug,
    sort_order: index,
    children: [],
  }));
}

function findInTree(nodes: CategoryNode[], slug: string): CategoryNode | null {
  for (const node of nodes) {
    if (node.slug === slug) return node;
    const found = findInTree(node.children, slug);
    if (found) return found;
  }
  return null;
}

export type CategoryLookup =
  | { status: "found"; name: string }
  | { status: "missing" }
  | { status: "unavailable" };

// Существует ли раздел и как он называется на витрине. Берём из дерева категорий:
// оно дешевле фасетов. «Нет раздела» и «нет связи» различаем принципиально — при
// недоступном API страница не должна превращаться в 404 для всего каталога.
export async function getCategoryLookup(slug: string): Promise<CategoryLookup> {
  const tree = await getCategoryTreeOrNull();
  if (!tree) return { status: "unavailable" };
  const found = findInTree(tree, slug);
  return found ? { status: "found", name: found.name } : { status: "missing" };
}

// Товары раздела для блока «подобрать по теме» в статье. Без API → пусто (блок скрыт).
export async function getCategoryProducts(category: string, limit = 3): Promise<Product[]> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchCategoryProductsFromApi(API_BASE, category, limit);
  }
  return [];
}

// Корневые категории (depth==1) для блока главной. Нет данных → пусто (блок скрыт).
export async function getCategoryTree(): Promise<CategoryNode[]> {
  if (API_BASE && !FORCE_FIXTURES) {
    return (await fetchCategoryTreeFromApi(API_BASE)) ?? [];
  }
  return [];
}

/**
 * Витрина главной. Возвращает и сами товары, и то, ЧЕМ они являются:
 * `bestsellers` — реальные продажи за окно (backend apps.catalog.sales),
 * `new` — продаж пока нет, показываем новинки под честным заголовком.
 * Без API → пусто (блок скрыт).
 */
export async function getBestsellers(
  limit = 8,
): Promise<{ products: Product[]; kind: "bestsellers" | "new" }> {
  if (API_BASE && !FORCE_FIXTURES) {
    return await fetchBestsellersFromApi(API_BASE, limit);
  }
  return { products: [], kind: "new" };
}
