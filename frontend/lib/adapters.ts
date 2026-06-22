// Адаптер DRF → UI. Изолирует форму ответа Django-каталога от витрины: при
// изменениях API правим только здесь. Эндпоинты (см. apps/catalog/api):
//   GET /api/catalog/products/?category=<slug>&brand=&stock_status=&price_min=&price_max=&limit=&offset=
//       → DRF LimitOffsetPagination: { count, next, previous, results: ApiProduct[] }
//   GET /api/catalog/categories/<slug>/facets/?brand=&stock_status=&attr_<slug>=
//       → { category, total_products, facets: ApiFacet[] }
//
// Ограничения текущего API (MVP, без правок бэкенда):
//  - список товаров не отдаёт характеристики → specs/energy-чип на карточке пустые;
//  - серверной сортировки нет (всегда по name);
//  - фасеты — только EAV-атрибуты (бренд/наличие/цена в этот эндпоинт не входят).

import type {
  Facet,
  Listing,
  ListingQuery,
  Product,
  StockState,
} from "./types";

// Внутренние server-side запросы Next→Django идут по http внутри Docker, а Django в prod
// редиректит http→https (SECURE_SSL_REDIRECT). Этот заголовок (ТОЛЬКО server-side!) сообщает
// Django через SECURE_PROXY_SSL_HEADER, что запрос защищён → без редиректа. Из браузера НЕ слать.
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;

// Ошибка обращения к каталог-API (не 404 категории) — должна вести в error.tsx, а не маскироваться.
export class CatalogFetchError extends Error {}

type ApiProduct = {
  id: number;
  name: string;
  slug: string;
  brand?: string | null;
  category?: { name?: string; slug?: string } | null;
  price?: string | null;
  old_price?: string | null;
  currency?: string | null;
  stock_status?: string | null;
  main_image?: string | null;
  short_description?: string | null;
};

type ApiFacetValue = { value: unknown; count: number; selected: boolean };
type ApiFacet = {
  slug: string;
  name: string;
  type: string; // text|integer|decimal|boolean|select|multiselect
  unit?: string;
  values?: ApiFacetValue[];
};

function num(v: unknown): number | undefined {
  if (v == null || v === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

function mapStock(s?: string | null): StockState {
  if (s === "in_stock") return "in";
  if (s === "on_order") return "order";
  return "out";
}

export function apiProductToProduct(ap: ApiProduct): Product {
  const final = num(ap.price);
  const old = num(ap.old_price);
  const hasDiscount = old != null && final != null && old > final;
  return {
    id: ap.id,
    slug: ap.slug,
    name: ap.name,
    brand: ap.brand ?? "",
    image: ap.main_image ?? undefined,
    specs: [],
    price: {
      final,
      old: hasDiscount ? old : undefined,
      discountPct: hasDiscount ? Math.round((1 - final! / old!) * 100) : undefined,
      currency: (ap.currency as "RUB") || "RUB",
    },
    stock: mapStock(ap.stock_status),
    badges: [],
  };
}

export function apiFacetToFacet(af: ApiFacet): Facet {
  // Код EAV-фасета храним С префиксом attr_ — это и есть имя query-параметра витрины и API
  // (attr_tool_type), однозначно отделённое от legacy-навигации ?tool_type=<slug> и UI-state.
  const code = `attr_${af.slug}`;
  const isRange = af.type === "integer" || af.type === "decimal";
  if (isRange) {
    const nums = (af.values ?? [])
      .map((v) => num(v.value))
      .filter((n): n is number => n != null);
    return {
      code,
      label: af.name,
      type: "range",
      unit: af.unit || undefined,
      min: nums.length ? Math.min(...nums) : undefined,
      max: nums.length ? Math.max(...nums) : undefined,
    };
  }
  return {
    code,
    label: af.name,
    type: "checkbox",
    unit: af.unit || undefined,
    options: (af.values ?? []).map((v) => ({
      value: String(v.value),
      label: String(v.value),
      count: v.count,
      selected: v.selected,
    })),
  };
}

function humanize(slug: string): string {
  return slug.replace(/[-_]/g, " ").replace(/^\p{L}/u, (c) => c.toUpperCase());
}

// query-параметры products-эндпоинта из нормализованного ListingQuery.
function buildProductParams(query: ListingQuery): URLSearchParams {
  const sp = new URLSearchParams();
  sp.set("category", query.category);
  sp.set("limit", String(query.perPage));
  sp.set("offset", String((query.page - 1) * query.perPage));

  const f = query.filters;
  const brand = f.brand;
  if (Array.isArray(brand) && brand.length) sp.set("brand", brand[0]); // API: один бренд

  const stock = f.stock;
  const stockMap: Record<string, string> = {
    in: "in_stock",
    order: "on_order",
    out: "out_of_stock",
  };
  if (Array.isArray(stock) && stock.length && stockMap[stock[0]]) {
    sp.set("stock_status", stockMap[stock[0]]);
  }

  const price = f.price;
  if (price && !Array.isArray(price)) {
    if (price.min != null) sp.set("price_min", String(price.min));
    if (price.max != null) sp.set("price_max", String(price.max));
  }

  // EAV-фасеты PLP: ключи фильтров с префиксом attr_ (напр. attr_tool_type) уходят в
  // products-эндпоинт как есть — тем же параметром, что и в фасеты (один механизм фильтрации).
  for (const [code, val] of Object.entries(f)) {
    if (!code.startsWith("attr_")) continue;
    if (Array.isArray(val)) for (const v of val) sp.append(code, v);
  }
  return sp;
}

function buildFacetParams(query: ListingQuery): URLSearchParams {
  const sp = new URLSearchParams();
  const f = query.filters;
  if (Array.isArray(f.brand)) for (const b of f.brand) sp.append("brand", b);
  const stockMap: Record<string, string> = {
    in: "in_stock",
    order: "on_order",
    out: "out_of_stock",
  };
  if (Array.isArray(f.stock) && f.stock.length && stockMap[f.stock[0]]) {
    sp.set("stock_status", stockMap[f.stock[0]]);
  }
  // EAV-фасеты уже имеют префикс attr_ в ключе фильтра → шлём как есть (attr_tool_type=value).
  for (const [code, val] of Object.entries(f)) {
    if (!code.startsWith("attr_")) continue;
    if (Array.isArray(val)) for (const v of val) sp.append(code, v);
  }
  return sp;
}

export async function fetchListingFromApi(
  base: string,
  query: ListingQuery,
): Promise<Listing | null> {
  const root = base.replace(/\/$/, "");

  const productsRes = await fetch(
    `${root}/api/catalog/products/?${buildProductParams(query).toString()}`,
    { cache: "no-store", headers: SSR_HEADERS },
  );
  if (productsRes.status === 404) return null;
  if (!productsRes.ok) throw new CatalogFetchError(`products ${productsRes.status}`);
  const productsJson = (await productsRes.json()) as {
    count: number;
    results: ApiProduct[];
  };

  // Фасеты — best-effort: если эндпоинт упал, страница всё равно отрендерится.
  let facets: Facet[] = [];
  try {
    const facetsRes = await fetch(
      `${root}/api/catalog/categories/${query.category}/facets/?${buildFacetParams(query).toString()}`,
      { cache: "no-store", headers: SSR_HEADERS },
    );
    if (facetsRes.ok) {
      const fj = (await facetsRes.json()) as { facets?: ApiFacet[] };
      facets = (fj.facets ?? []).map(apiFacetToFacet);
    }
  } catch {
    facets = [];
  }

  const products = productsJson.results.map(apiProductToProduct);
  const categoryName =
    productsJson.results[0]?.category?.name ?? humanize(query.category);

  return {
    category: {
      title: categoryName,
      intro: "",
      breadcrumb: [
        { label: "Главная", href: "/" },
        { label: categoryName, href: `/catalog/${query.category}` },
      ],
    },
    subcategories: [],
    facets,
    sort: [],
    total: productsJson.count,
    page: query.page,
    perPage: query.perPage,
    products,
  };
}
