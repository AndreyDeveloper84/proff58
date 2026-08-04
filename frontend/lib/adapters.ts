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

import { BASE_FACET_CODES } from "./constants";
import { formatRu, humanizeToken } from "./format";
import type {
  CompatibilitySections,
  Facet,
  FacetGroupKind,
  FilterMode,
  Listing,
  ListingQuery,
  Product,
  ProductDetail,
  ProductImageData,
  StockState,
} from "./types";

// Код фасета базовый? (§3.3/§6 — видим всегда). Список — в constants (по коду, не по названию).
const BASE_CODES: ReadonlySet<string> = new Set(BASE_FACET_CODES);

// Внутренние server-side запросы Next→Django идут по http внутри Docker, а Django в prod
// редиректит http→https (SECURE_SSL_REDIRECT). Этот заголовок (ТОЛЬКО server-side!) сообщает
// Django через SECURE_PROXY_SSL_HEADER, что запрос защищён → без редиректа. Из браузера НЕ слать.
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;

// Таймаут внутренних SSR-запросов главной. Без него зависший апстрим вешает
// рендер `/` навечно (fetch без таймаута) и копит воркеры. С таймаутом запрос
// прерывается, существующий catch → пустой блок (мягкая деградация).
const SSR_TIMEOUT_MS = 4000;

// Ошибка обращения к каталог-API (не 404 категории) — должна вести в error.tsx, а не маскироваться.
export class CatalogFetchError extends Error {}

type ApiAttr = { name: string; slug: string; unit?: string; value: unknown };
type ApiProduct = {
  id: number;
  name: string;
  // Короткая форма для плитки; backend отдаёт витринное имя, если она не задана.
  card_name?: string | null;
  slug: string;
  brand?: string | null;
  category?: { name?: string; slug?: string } | null;
  price?: string | null;
  old_price?: string | null;
  currency?: string | null;
  stock_status?: string | null;
  stock_qty?: number | null;
  main_image?: string | null;
  short_description?: string | null;
  attributes?: ApiAttr[];
  // Рейтинг продаж backend: товар в топе продаж за окно (apps.catalog.sales).
  is_hit?: boolean;
};

type ApiImage = { url: string; alt?: string | null; is_main?: boolean };
// Detail-эндпоинт (/products/{slug}/) = ApiProduct + description/images/breadcrumb.
type ApiProductDetail = ApiProduct & {
  description?: string | null;
  video_url?: string | null;
  images?: ApiImage[];
  breadcrumb?: { name: string; slug: string }[];
};
// /products/{slug}/compatible/ — секции связанных товаров (ApiProduct + опц. note).
type ApiCompatibleResponse = {
  accessories?: ApiProduct[];
  cross_sell?: ApiProduct[];
  analogs?: ApiProduct[];
  fits?: ApiProduct[];
  compatible?: ApiProduct[];
};

type ApiBrand = { value: string; label: string; count: number; selected: boolean };
type ApiStock = { value: string; label: string; count: number; selected: boolean };
type ApiCategoryBlock = {
  name: string;
  slug: string;
  description?: string;
  breadcrumb?: { name: string; slug: string }[];
  hero?: {
    image: string | null;
    eyebrow?: string;
  };
};
type ApiFacetsResponse = {
  category?: ApiCategoryBlock;
  subcategories?: { name: string; slug: string }[];
  price?: { min: number | null; max: number | null };
  brands?: ApiBrand[];
  stock?: ApiStock[];
  // §3.4: сырое поле API (любая строка); доверяем только после whitelist-проверки asFilterMode.
  category_filter_mode?: string;
  facets?: ApiFacet[];
};

// Сужение сырого значения API к FilterMode (или undefined → авто-определение во фронте).
function asFilterMode(v: unknown): FilterMode | undefined {
  return v === "broad" || v === "typed" || v === "leaf" ? v : undefined;
}

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
  // Навигационный фасет (tool_type): рендерится блоком навигации, выбор → верхнеуровневый ?tool_type=.
  is_nav?: boolean;
  // Раздел сайдбара (§22.4, D1): "main"|"extra". Любая иная/пустая строка → main (дефолт).
  group?: string;
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
  else if (typeof value === "number") s = formatRu(value);
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
    cardName: ap.card_name || ap.name,
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
    stockQty: ap.stock_qty ?? undefined,
    // sale — из скидки, hit — из рейтинга продаж backend (apps.catalog.sales):
    // бейдж «Хит» означает реальные продажи за окно, а не редакторскую пометку.
    // new — по-прежнему вне scope: надёжного признака новизны нет.
    badges: [
      ...(ap.is_hit ? (["hit"] as const) : []),
      ...(hasDiscount ? (["sale"] as const) : []),
    ],
  };
}

function apiProductToDetail(ap: ApiProductDetail): ProductDetail {
  const base = apiProductToProduct(ap);
  const images: ProductImageData[] = (ap.images ?? [])
    .filter((im) => im && im.url)
    .map((im) => ({ url: im.url, alt: im.alt || base.name, isMain: im.is_main === true }));
  // main_image как fallback, если detail не отдал галерею.
  if (!images.length && base.image) {
    images.push({ url: base.image, alt: base.name, isMain: true });
  }
  // главное фото — первым (isMain), затем остальные.
  images.sort((a, b) => Number(b.isMain) - Number(a.isMain));
  return {
    ...base,
    images,
    description: ap.description ?? "",
    videoUrl: ap.video_url ?? undefined,
    breadcrumb: ap.breadcrumb ?? [],
  };
}

// --- фасеты price/brand/stock из нового facets-контракта (B0) — всегда kind: "base" (§6.2) ---
function priceFacet(price?: { min: number | null; max: number | null }): Facet | null {
  if (!price || price.min == null || price.max == null) return null;
  return {
    code: "price",
    label: "Цена",
    type: "range",
    unit: "₽",
    kind: "base",
    min: price.min,
    max: price.max,
  };
}
function stockFacet(stock?: ApiStock[]): Facet | null {
  if (!stock || !stock.length) return null;
  return {
    code: "stock",
    label: "Наличие",
    type: "checkbox",
    kind: "base",
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
    kind: "base",
    options: brands.map((b) => ({
      value: b.value,
      label: b.label,
      count: b.count,
      selected: b.selected,
    })),
  };
}

export function apiFacetToFacet(af: ApiFacet): Facet {
  // Классификация nav vs обычный фасет. tool_type (is_nav) — НАВИГАЦИЯ: код = bare slug
  // (tool_type), выбор идёт верхнеуровневым ?tool_type=, рендер — блок навигации. Остальные EAV
  // хранятся С префиксом attr_ — это имя query-параметра сайдбар-фильтра (attr_<slug>).
  const isNav = af.is_nav === true;
  const code = isNav ? af.slug : `attr_${af.slug}`;
  // Гейтинг-класс (§3.3/§6): nav → блок навигации; базовый код (напр. attr_power_source) → base;
  // прочие attr_* → tech (скрыты до выбора tool_type). По коду, не по названию.
  const kind: Facet["kind"] = isNav ? "nav" : BASE_CODES.has(code) ? "base" : "tech";
  // Группа сайдбара (§22.4, D2): доверяем только whitelisted "extra"; всё прочее (включая
  // "main"/пусто/мусор) → undefined, что группировка трактует как «Основные». Осмыслена
  // лишь для технических фасетов — для base/nav группа игнорируется при разбиении на секции.
  const group: FacetGroupKind | undefined = af.group === "extra" ? "extra" : undefined;
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
      isNav,
      kind,
      group,
      min: nums.length ? Math.min(...nums) : undefined,
      max: nums.length ? Math.max(...nums) : undefined,
    };
  }
  return {
    code,
    label: af.name,
    type: "checkbox",
    unit: af.unit || undefined,
    isNav,
    kind,
    group,
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

const humanize = humanizeToken; // алиас: единый источник в lib/format (N4)

// query-параметры products-эндпоинта из нормализованного ListingQuery.
function buildProductParams(query: ListingQuery): URLSearchParams {
  const sp = new URLSearchParams();
  sp.set("category", query.category);
  sp.set("limit", String(query.perPage));
  sp.set("offset", String((query.page - 1) * query.perPage));

  // tool_type — навигация: верхнеуровневый ?tool_type=<slug> (тот же параметр, что в facets,
  // — list и фасеты сужаются одним relational-механизмом, A1/#223).
  if (query.toolType) sp.set("tool_type", query.toolType);

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
  // Чекбоксы → attr_x=v; числовой диапазон → attr_x_min / attr_x_max.
  for (const [code, val] of Object.entries(f)) {
    if (!code.startsWith("attr_")) continue;
    if (Array.isArray(val)) {
      for (const v of val) sp.append(code, v);
    } else if (val) {
      if (val.min != null) sp.set(`${code}_min`, String(val.min));
      if (val.max != null) sp.set(`${code}_max`, String(val.max));
    }
  }

  // Серверная сортировка: дефолт (popular) бэку не шлём (он и так по name). rating бэк
  // приводит к дефолту, пока нет поля рейтинга.
  if (query.sort && query.sort !== "popular") sp.set("sort", query.sort);
  return sp;
}

function buildFacetParams(query: ListingQuery): URLSearchParams {
  const sp = new URLSearchParams();
  // tool_type → facets-эндпоинт: панель типов (own-axis) и прочие фасеты сужаются так же,
  // как список (A1/#223). Без этого counts разошлись бы с выдачей.
  if (query.toolType) sp.set("tool_type", query.toolType);
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
  // EAV-фасеты уже имеют префикс attr_ в ключе фильтра → шлём как есть: чекбоксы attr_x=value,
  // числовой диапазон attr_x_min / attr_x_max (drill-down счётчиков учитывает выбранный диапазон).
  for (const [code, val] of Object.entries(f)) {
    if (!code.startsWith("attr_")) continue;
    if (Array.isArray(val)) {
      for (const v of val) sp.append(code, v);
    } else if (val) {
      if (val.min != null) sp.set(`${code}_min`, String(val.min));
      if (val.max != null) sp.set(`${code}_max`, String(val.max));
    }
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
  // Исключение — 404: этот эндпоинт отдаёт его только когда категории с таким slug нет
  // (или она снята с публикации), и это единственный признак несуществующего раздела —
  // products/?category=<мусор> отвечает 200 с пустым списком. Без него страница
  // превращалась бы в soft-404: HTTP 200 с пустым листингом и заголовком из slug.
  let facets: Facet[] = [];
  let categoryBlock: ApiCategoryBlock | undefined;
  let subcategories: { label: string; href: string }[] = [];
  let filterMode: FilterMode | undefined;
  let categoryMissing = false;
  try {
    const facetsRes = await fetch(
      `${root}/api/catalog/categories/${encodeURIComponent(query.category)}/facets/?${buildFacetParams(query).toString()}`,
      { cache: "no-store", headers: SSR_HEADERS },
    );
    if (facetsRes.status === 404) {
      categoryMissing = true;
    } else if (facetsRes.ok) {
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
      filterMode = asFilterMode(fj.category_filter_mode);
      subcategories = (fj.subcategories ?? []).map((s) => ({
        label: s.name,
        href: `/catalog/${s.slug}`,
      }));
    }
  } catch {
    facets = [];
  }
  if (categoryMissing) return null; // → notFound() в page.tsx

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
      breadcrumb: [
        { label: "Главная", href: "/" },
        { label: "Каталог", href: "/catalog" },
        ...crumbs,
      ],
      hero: categoryBlock?.hero
        ? {
            image: categoryBlock.hero.image ?? null,
            eyebrow: categoryBlock.hero.eyebrow ?? "",
          }
        : undefined,
    },
    filterMode,
    subcategories,
    facets,
    sort: [],
    total: productsJson.count,
    page: query.page,
    perPage: query.perPage,
    products,
  };
}

// Поиск по каталогу (SSR-страница /search): ProductListView c ?search= ранжирует по
// релевантности (trigram). Серверный вызов Next→Django (как fetchListingFromApi). Запрос
// короче 2 символов или сбой API → пустой список (страница покажет «ничего не найдено»).
export async function fetchSearchFromApi(base: string, q: string): Promise<Product[]> {
  const query = q.trim();
  if (query.length < 2) return [];
  const root = base.replace(/\/$/, "");
  const res = await fetch(
    `${root}/api/catalog/products/?search=${encodeURIComponent(query)}`,
    { cache: "no-store", headers: SSR_HEADERS },
  );
  if (!res.ok) return [];
  const json = (await res.json()) as { results?: ApiProduct[] };
  return (json.results ?? []).map(apiProductToProduct);
}

// Карточка товара (PDP): detail-эндпоинт + best-effort секции совместимости.
// 404 → null (→ notFound() в page.tsx); иная ошибка detail → CatalogFetchError (→ error.tsx).
export async function fetchProductFromApi(
  base: string,
  slug: string,
): Promise<ProductDetail | null> {
  const root = base.replace(/\/$/, "");
  const res = await fetch(`${root}/api/catalog/products/${encodeURIComponent(slug)}/`, {
    cache: "no-store",
    headers: SSR_HEADERS,
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new CatalogFetchError(`product ${res.status}`);
  const detail = await fetchProductCompatible(root, slug);
  return { ...apiProductToDetail((await res.json()) as ApiProductDetail), compatible: detail };
}

// Секции совместимости — best-effort: упал эндпоинт → пустые секции, карточка всё равно рендерится.
async function fetchProductCompatible(
  root: string,
  slug: string,
): Promise<CompatibilitySections> {
  const empty: CompatibilitySections = {
    accessories: [],
    crossSell: [],
    analogs: [],
    fits: [],
    compatible: [],
  };
  try {
    const res = await fetch(
      `${root}/api/catalog/products/${encodeURIComponent(slug)}/compatible/`,
      { cache: "no-store", headers: SSR_HEADERS },
    );
    if (!res.ok) return empty;
    const cj = (await res.json()) as ApiCompatibleResponse;
    return {
      accessories: (cj.accessories ?? []).map(apiProductToProduct),
      crossSell: (cj.cross_sell ?? []).map(apiProductToProduct),
      analogs: (cj.analogs ?? []).map(apiProductToProduct),
      fits: (cj.fits ?? []).map(apiProductToProduct),
      compatible: (cj.compatible ?? []).map(apiProductToProduct),
    };
  } catch {
    return empty;
  }
}

// --- Главная страница ---

export type CategoryNode = {
  id: number;
  name: string;
  slug: string;
  sort_order: number;
  children: CategoryNode[];
};

// Дерево категорий (корни + потомки). null — API недоступен или ответил невалидом;
// [] — категорий нет. Разницу использует индекс каталога («временно недоступен» vs
// «разделы не заполнены»); главная обе ситуации деградирует одинаково — скрывает блок.
export async function fetchCategoryTreeFromApi(base: string): Promise<CategoryNode[] | null> {
  const root = base.replace(/\/$/, "");
  try {
    const res = await fetch(`${root}/api/catalog/categories/`, {
      cache: "no-store",
      headers: SSR_HEADERS,
      signal: AbortSignal.timeout(SSR_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const json = (await res.json()) as CategoryNode[];
    return Array.isArray(json) ? json : null;
  } catch {
    return null;
  }
}

// Товары раздела для блока «подобрать по теме» в статьях. Best-effort: сбой →
// пустой список, блок просто не отрисуется (статья ценна и без витрины).
/**
 * Карточки товаров по списку id — для избранного (?ids=).
 *
 * limit, а не page_size: пагинация каталога — LimitOffsetPagination, и без
 * явного лимита ответ обрезала бы страница по умолчанию (24 позиции).
 * Порядок ответа не гарантирован, его выстраивает вызывающий.
 */
export async function fetchProductsByIdsFromApi(base: string, ids: number[]): Promise<Product[]> {
  if (ids.length === 0) return [];
  const root = base.replace(/\/$/, "");
  const params = new URLSearchParams({ ids: ids.join(","), limit: String(ids.length) });
  const res = await fetch(`${root}/api/catalog/products/?${params.toString()}`, {
    cache: "no-store",
    headers: SSR_HEADERS,
    signal: AbortSignal.timeout(SSR_TIMEOUT_MS),
  });
  if (!res.ok) throw new CatalogFetchError(`Каталог ответил ${res.status}`);
  const json = (await res.json()) as { results?: ApiProduct[] };
  return (json.results ?? []).map(apiProductToProduct);
}

export async function fetchCategoryProductsFromApi(
  base: string,
  category: string,
  limit: number,
): Promise<Product[]> {
  const root = base.replace(/\/$/, "");
  try {
    const res = await fetch(
      // limit, а не page_size: пагинация каталога — LimitOffsetPagination, и
      // page_size она просто игнорирует. Работало по случайности: ответ приходил
      // страницей по умолчанию (24 позиции), лишнее срезал slice ниже.
      `${root}/api/catalog/products/?category=${encodeURIComponent(category)}&limit=${limit}`,
      { cache: "no-store", headers: SSR_HEADERS, signal: AbortSignal.timeout(SSR_TIMEOUT_MS) },
    );
    if (!res.ok) return [];
    const json = (await res.json()) as { results?: ApiProduct[] };
    return (json.results ?? []).slice(0, limit).map(apiProductToProduct);
  } catch {
    return [];
  }
}

// «Хиты продаж»: курируемые slug'и (detail-эндпоинт, параллельно) → fallback ?sort=new.
// Detail-ответ — надмножество list (ApiProduct), apiProductToProduct берёт нужное подмножество.
/**
 * Витрина главной: реальные хиты продаж, иначе — честно помеченные новинки.
 *
 * `kind` существует именно ради честности заголовка. Раньше блок «Хиты продаж»
 * молча показывал `?sort=new`, то есть выдавал новинки за хиты. Теперь источник
 * выдачи виден вызывающему, и подпись блока меняется вместе с ним.
 */
export async function fetchBestsellersFromApi(
  base: string,
  limit: number,
): Promise<{ products: Product[]; kind: "bestsellers" | "new" }> {
  const root = base.replace(/\/$/, "");

  const load = async (path: string): Promise<Product[]> => {
    try {
      const res = await fetch(`${root}${path}`, {
        cache: "no-store",
        headers: SSR_HEADERS,
        signal: AbortSignal.timeout(SSR_TIMEOUT_MS),
      });
      if (!res.ok) return [];
      const json = (await res.json()) as { results?: ApiProduct[] };
      return (json.results ?? []).map(apiProductToProduct);
    } catch {
      return [];
    }
  };

  // Эндпоинт хитов отдаёт ТОЛЬКО товары с продажами за окно: пустой ответ здесь —
  // это «продаж пока нет», а не сбой, и подменять его нечем.
  const bestsellers = await load(`/api/catalog/bestsellers/?limit=${limit}`);
  if (bestsellers.length) return { products: bestsellers, kind: "bestsellers" };

  return { products: await load(`/api/catalog/products/?sort=new&limit=${limit}`), kind: "new" };
}

// #573: первая страница отзывов товара + агрегат — SSR напрямую в Django
// (SEO; флаг reviews off → 404 → null → секция не рендерится, без мигания).
export async function fetchProductReviewsFromApi(
  root: string,
  slug: string,
): Promise<import("./types").ProductReviewsPayload | null> {
  try {
    const res = await fetch(
      `${root}/api/reviews/product/${encodeURIComponent(slug)}/?limit=10`,
      { cache: "no-store", headers: { "X-Forwarded-Proto": "https" } },
    );
    if (!res.ok) return null;
    return (await res.json()) as import("./types").ProductReviewsPayload;
  } catch {
    return null;
  }
}
