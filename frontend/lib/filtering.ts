// Клиентская фильтрация/сортировка фикстуры + пересчёт счётчиков фасетов (faceted).
// Чистые функции — переиспользуются в ListingShell и в тестах.

import { BRAND_SLUGS, CHUCK_SLUGS } from "./constants";
import type { Facet, Listing, ListingQuery, Product, RangeFilterValue } from "./types";

export function parseNum(s?: string | number | null): number | undefined {
  if (s == null) return undefined;
  if (typeof s === "number") return Number.isFinite(s) ? s : undefined;
  const m = s.replace(",", ".").match(/-?\d+(\.\d+)?/);
  return m ? Number(m[0]) : undefined;
}

function isRange(v: string[] | RangeFilterValue): v is RangeFilterValue {
  return !Array.isArray(v);
}

// Значение товара для чекбокс-фасета (как option.value, латиницей/slug).
function checkboxValue(p: Product, code: string): string | undefined {
  switch (code) {
    case "brand":
      return BRAND_SLUGS[p.brand] ?? p.brand.toLowerCase();
    case "stock":
      return p.stock;
    case "chuck":
      return p.chuck ? (CHUCK_SLUGS[p.chuck] ?? p.chuck.toLowerCase()) : undefined;
    default:
      return undefined;
  }
}

// Числовое значение товара для диапазонного фасета.
function rangeValue(p: Product, code: string): number | undefined {
  switch (code) {
    case "price":
      return p.price.final;
    case "energy_impact":
      return parseNum(p.energy);
    default:
      return undefined;
  }
}

function matchesOne(p: Product, code: string, val: string[] | RangeFilterValue): boolean {
  if (isRange(val)) {
    const n = rangeValue(p, code);
    if (n == null) return false;
    if (val.min != null && n < val.min) return false;
    if (val.max != null && n > val.max) return false;
    return true;
  }
  if (val.length === 0) return true;
  const pv = checkboxValue(p, code);
  return pv != null && val.includes(pv);
}

export function matchesFilters(
  p: Product,
  filters: ListingQuery["filters"],
  except?: string,
): boolean {
  return Object.entries(filters).every(
    ([code, val]) => code === except || matchesOne(p, code, val),
  );
}

function sortProducts(arr: Product[], sort: ListingQuery["sort"]): Product[] {
  const s = [...arr];
  switch (sort) {
    case "price_asc":
      s.sort((a, b) => (a.price.final ?? Infinity) - (b.price.final ?? Infinity));
      break;
    case "price_desc":
      s.sort((a, b) => (b.price.final ?? -Infinity) - (a.price.final ?? -Infinity));
      break;
    case "rating":
      s.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
      break;
    case "new":
      s.sort(
        (a, b) => Number(b.badges.includes("new")) - Number(a.badges.includes("new")),
      );
      break;
    default:
      break; // popular — исходный порядок фикстуры
  }
  return s;
}

export type ListingResult = {
  products: Product[]; // товары текущей страницы
  total: number; // всего после фильтров
  page: number;
  totalPages: number;
  facets: Facet[]; // со свежими count + selected
};

export function applyListing(listing: Listing, query: ListingQuery): ListingResult {
  const all = listing.products;
  const filtered = all.filter((p) => matchesFilters(p, query.filters));
  const sorted = sortProducts(filtered, query.sort);

  const total = sorted.length;
  const totalPages = Math.max(1, Math.ceil(total / query.perPage));
  const page = Math.min(Math.max(1, query.page), totalPages);
  const start = (page - 1) * query.perPage;
  const products = sorted.slice(start, start + query.perPage);

  // Счётчик каждого значения — по выборке со ВСЕМИ фильтрами, КРОМЕ этого фасета.
  const facets = listing.facets.map((f): Facet => {
    if (f.type !== "checkbox" || !f.options) return { ...f };
    const base = all.filter((p) => matchesFilters(p, query.filters, f.code));
    const sel = query.filters[f.code];
    const selectedVals = Array.isArray(sel) ? sel : [];
    const options = f.options.map((o) => ({
      ...o,
      count: base.filter((p) => checkboxValue(p, f.code) === o.value).length,
      selected: selectedVals.includes(o.value),
    }));
    return { ...f, options };
  });

  return { products, total, page, totalPages, facets };
}
