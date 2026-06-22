// Адаптер DRF → UI. Изолирует форму ответа Django-каталога от витрины: при
// изменениях API правим только здесь. Эндпоинты (см. apps/catalog/api):
//   GET /api/catalog/products/?category=<slug>&brand=&stock_status=&price_min=&price_max=&limit=&offset=
//       → DRF LimitOffsetPagination: { count, next, previous, results: ApiProduct[] }
//   GET /api/catalog/categories/<slug>/facets/?brand=&stock_status=&attr_<slug>=
//       → { category, total_products, facets: ApiFacet[] }
//
// Контракт PLP (после насыщения API):
//  - list отдаёт `attributes` → строка спеков и спец-чип карточки;
//  - серверная сортировка через ?sort (price_asc|price_desc|new), дефолт — name;
//  - facets-эндпоинт отдаёт price/brands/stock + category/subcategories помимо EAV-атрибутов.

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

type ApiAttr = { name: string; slug: string; unit?: string; value: unknown };
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
  attributes?: ApiAttr[];
};

type ApiBrand = { value: string; label: string; count: number; selected: boolean };
type ApiStock = { value: string; label: string; count: number; selected: boolean };
type ApiCategoryBlock = {
  name: string;
  slug: string;
  description?: string;
  breadcrumb?: { name: string; slug: string }[];
};
type ApiFacetsResponse = {
  category?: ApiCategoryBlock;
  subcategories?: { name: string; slug: string }[];
  price?: { min: number | null; max: number | null };
  brands?: ApiBrand[];
  stock?: ApiStock[];
  facets?: ApiFacet[];
};

type ApiFacetValue = {
  value: unknown;
  // preferred URL token (slug-URL, P2); присутствует только когда у опции задан slug — иначе fallback на value
  slug?: string;
  count: number;
  selected: boolean;
};
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

// in_stock|on_order|out_of_stock (API) → UI-значение фильтра наличия.
const STOCK_API_TO_UI: Record<string, StockState> = {
  in_stock: "in",
  on_order: "order",
  out_of_stock: "out",
};

// Значение характеристики → строка карточки (RU-формат: десятичные через запятую; unit
// добавляем, только если его ещё нет в значении). «2 Дж», не «2.0 Дж».
function formatSpecValue(value: unknown, unit?: string): string {
  if (value == null || value === "") return "";
  let s: string;
  if (typeof value === "boolean") s = value ? "Да" : "Нет";
  else if (typeof value === "number") s = String(value).replace(".", ",");
  else s = String(value);
  const u = (unit ?? "").trim();
  if (u && !s.includes(u)) s = `${s} ${u}`;
  return s.trim();
}

export function apiProductToProduct(ap: ApiProduct): Product {
  const final = num(ap.price);
  const old = num(ap.old_price);
  const hasDiscount = old != null && final != null && old > final;
  const attrs = ap.attributes ?? [];
  const bySlug = (slug: string): string | undefined => {
    const a = attrs.find((x) => x.slug === slug);
    return a ? formatSpecValue(a.value, a.unit) || undefined : undefined;
  };
  return {
    id: ap.id,
    slug: ap.slug,
    name: ap.name,
    brand: ap.brand ?? "",
    image: ap.main_image ?? undefined,
    specs: attrs
      .map((a) => ({ label: a.name, value: formatSpecValue(a.value, a.unit) }))
      .filter((s) => s.value),
    energy: bySlug("energy_impact"),
    power: bySlug("power"),
    chuck: bySlug("chuck"),
    price: {
      final,
      old: hasDiscount ? old : undefined,
      discountPct: hasDiscount ? Math.round((1 - final! / old!) * 100) : undefined,
      currency: (ap.currency as "RUB") || "RUB",
    },
    stock: mapStock(ap.stock_status),
    // sale — из скидки (данные есть). new/hit — вне scope (нет надёжного признака новизны).
    badges: hasDiscount ? ["sale"] : [],
  };
}

// --- фасеты price/brand/stock из нового facets-контракта (B0) ---
function priceFacet(price?: { min: number | null; max: number | null }): Facet | null {
  if (!price || price.min == null || price.max == null) return null;
  return { code: "price", label: "Цена", type: "range", unit: "₽", min: price.min, max: price.max };
}
function stockFacet(stock?: ApiStock[]): Facet | null {
  if (!stock || !stock.length) return null;
  return {
    code: "stock",
    label: "Наличие",
    type: "checkbox",
    options: stock.map((s) => ({
      value: STOCK_API_TO_UI[s.value] ?? s.value,
      label: s.label,
      count: s.count,
      selected: s.selected,
    })),
  };
}
function brandFacet(brands?: ApiBrand[]): Facet | null {
  if (!brands || !brands.length) return null;
  return {
    code: "brand",
    label: "Бренд",
    type: "checkbox",
    options: brands.map((b) => ({
      value: b.value,
      label: b.label,
      count: b.count,
      selected: b.selected,
    })),
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
      // value — токен для URL/фильтра: canonical slug, если он есть, иначе raw value (legacy)
      value: String(v.slug ?? v.value),
      // label — то, что видит пользователь (всегда человекочитаемое raw value)
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

  // Серверная сортировка: дефолт (popular) бэку не шлём (он и так по name). rating бэк
  // приводит к дефолту, пока нет поля рейтинга.
  if (query.sort && query.sort !== "popular") sp.set("sort", query.sort);
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
  // Цена в facets-запрос → drill-down счётчиков brand/stock/attr учитывает выбранную цену.
  const price = f.price;
  if (price && !Array.isArray(price)) {
    if (price.min != null) sp.set("price_min", String(price.min));
    if (price.max != null) sp.set("price_max", String(price.max));
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

  // Фасеты + метаданные категории — best-effort: упал эндпоинт → страница всё равно рендерится.
  let facets: Facet[] = [];
  let categoryBlock: ApiCategoryBlock | undefined;
  let subcategories: { label: string; href: string }[] = [];
  try {
    const facetsRes = await fetch(
      `${root}/api/catalog/categories/${query.category}/facets/?${buildFacetParams(query).toString()}`,
      { cache: "no-store", headers: SSR_HEADERS },
    );
    if (facetsRes.ok) {
      const fj = (await facetsRes.json()) as ApiFacetsResponse;
      const attrFacets = (fj.facets ?? []).map(apiFacetToFacet);
      // Порядок макета: Цена → Наличие → Бренд → атрибутные фасеты.
      facets = [
        priceFacet(fj.price),
        stockFacet(fj.stock),
        brandFacet(fj.brands),
        ...attrFacets,
      ].filter((x): x is Facet => x != null);
      categoryBlock = fj.category;
      subcategories = (fj.subcategories ?? []).map((s) => ({
        label: s.name,
        href: `/catalog/${s.slug}`,
      }));
    }
  } catch {
    facets = [];
  }

  const products = productsJson.results.map(apiProductToProduct);
  const categoryName =
    categoryBlock?.name ?? productsJson.results[0]?.category?.name ?? humanize(query.category);
  const crumbs =
    categoryBlock?.breadcrumb && categoryBlock.breadcrumb.length
      ? categoryBlock.breadcrumb.map((c) => ({ label: c.name, href: `/catalog/${c.slug}` }))
      : [{ label: categoryName, href: `/catalog/${query.category}` }];

  return {
    category: {
      title: categoryName,
      intro: categoryBlock?.description ?? "",
      breadcrumb: [{ label: "Главная", href: "/" }, ...crumbs],
    },
    subcategories,
    facets,
    sort: [],
    total: productsJson.count,
    page: query.page,
    perPage: query.perPage,
    products,
  };
}
