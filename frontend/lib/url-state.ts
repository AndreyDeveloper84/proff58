// Единственный источник состояния PLP: разбор и сборка searchParams.
// URL-контракт — только slug/латиница (без кириллицы), напр.:
//   ?brand=bosch,makita ?stock=in ?price_min=3000&price_max=25000
//   ?energy_impact_min=2&energy_impact_max=4 ?chuck=sds-plus
//   ?sort=price_asc ?page=2&per_page=24 ?view=grid
// Смена любого фильтра сбрасывает page=1 (делает вызывающий код в ListingShell).

import {
  CHECKBOX_FACETS,
  DEFAULT_PER_PAGE,
  DEFAULT_SORT,
  NAV_ATTR_KEYS,
  PER_PAGE_OPTIONS,
  RANGE_FACETS,
  RESERVED_QUERY_PARAMS,
} from "./constants";
import type { ListingQuery, RangeFilterValue, SortOption } from "./types";

const SORTS: SortOption[] = [
  "popular",
  "bestsellers",
  "price_asc",
  "price_desc",
  "new",
  "rating",
];

function num(v: string | null): number | undefined {
  if (v == null || v === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

export function parseQuery(sp: URLSearchParams, category: string): ListingQuery {
  const sortRaw = sp.get("sort") as SortOption | null;
  const sort = sortRaw && SORTS.includes(sortRaw) ? sortRaw : DEFAULT_SORT;

  const view = sp.get("view") === "list" ? "list" : "grid";

  const perPageRaw = num(sp.get("per_page")) ?? DEFAULT_PER_PAGE;
  const perPage = (PER_PAGE_OPTIONS as readonly number[]).includes(perPageRaw)
    ? perPageRaw
    : DEFAULT_PER_PAGE;

  const page = Math.max(1, Math.trunc(num(sp.get("page")) ?? 1));

  // tool_type — верхнеуровневый навигационный параметр (§5.1). Приоритет у tool_type над
  // legacy attr_tool_type: последний для ТИПА не парсим в filters (см. цикл attr_ ниже).
  const toolTypeRaw = (sp.get("tool_type") ?? "").trim();
  const toolType = toolTypeRaw || undefined;

  const filters: ListingQuery["filters"] = {};

  for (const code of CHECKBOX_FACETS) {
    const raw = sp.get(code);
    if (!raw) continue;
    const vals = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (vals.length) filters[code] = vals;
  }

  for (const code of RANGE_FACETS) {
    const min = num(sp.get(`${code}_min`));
    const max = num(sp.get(`${code}_max`));
    if (min != null || max != null) filters[code] = { min, max } as RangeFilterValue;
  }

  // Динамические EAV-фасеты приходят из API с префиксом attr_ (коды заранее не известны →
  // парсим по префиксу, а не по белому списку): чекбоксы (attr_x=v1,v2) и числовые
  // диапазоны (attr_x_min / attr_x_max → {min,max}). RESERVED_QUERY_PARAMS не нужны
  // (attr_ их и так исключает), но проверяем для надёжности.
  for (const key of new Set(sp.keys())) {
    if (!key.startsWith("attr_") || RESERVED_QUERY_PARAMS.has(key)) continue;
    // attr_tool_type* — это ТИП (навигация). Канонический параметр — верхнеуровневый
    // tool_type, поэтому в filters не кладём (§5.1, приоритет tool_type).
    if (NAV_ATTR_KEYS.has(key)) continue;
    if (key.endsWith("_min") || key.endsWith("_max")) {
      const code = key.slice(0, -4); // отрезаем _min/_max → базовый код фасета
      if (code.length <= "attr_".length || filters[code]) continue; // attr__min и т.п. — мусор
      const min = num(sp.get(`${code}_min`));
      const max = num(sp.get(`${code}_max`));
      if (min != null || max != null) filters[code] = { min, max } as RangeFilterValue;
      continue;
    }
    if (filters[key]) continue;
    const raw = sp.get(key);
    if (!raw) continue;
    const vals = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (vals.length) filters[key] = vals;
  }

  return { category, page, perPage, sort, view, toolType, filters };
}

export function serializeQuery(q: ListingQuery): string {
  const sp = new URLSearchParams();

  // tool_type — верхнеуровневый навигационный параметр (не filters, не attr_*; §5.1).
  if (q.toolType) sp.set("tool_type", q.toolType);

  for (const [code, val] of Object.entries(q.filters)) {
    if (NAV_ATTR_KEYS.has(code)) continue; // тип сериализуем только как tool_type (§5.1)
    if (Array.isArray(val)) {
      if (val.length) sp.set(code, val.join(","));
    } else {
      if (val.min != null) sp.set(`${code}_min`, String(val.min));
      if (val.max != null) sp.set(`${code}_max`, String(val.max));
    }
  }

  if (q.sort !== DEFAULT_SORT) sp.set("sort", q.sort);
  if (q.view !== "grid") sp.set("view", q.view);
  if (q.perPage !== DEFAULT_PER_PAGE) sp.set("per_page", String(q.perPage));
  if (q.page > 1) sp.set("page", String(q.page));

  return sp.toString();
}
