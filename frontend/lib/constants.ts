import type { SortOption } from "./types";

export const PER_PAGE_OPTIONS = [12, 24, 48] as const;
export const DEFAULT_PER_PAGE = 24;
export const DEFAULT_SORT: SortOption = "popular";

export const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "popular", label: "По умолчанию" },
  { value: "price_asc", label: "Сначала дешёвые" },
  { value: "price_desc", label: "Сначала дорогие" },
  { value: "new", label: "Новинки" },
  { value: "rating", label: "По рейтингу" },
];

// Диапазонные фасеты — в URL как code_min / code_max.
export const RANGE_FACETS = ["price", "energy_impact"] as const;
// Чекбокс-фасеты — в URL как code=val1,val2.
export const CHECKBOX_FACETS = ["brand", "stock", "chuck"] as const;

// UI-state и трекинговые параметры: НЕ являются фильтрами, не должны попадать в filters
// при разборе динамических EAV-фасетов (attr_*). Защита от utm_*/q/search и т.п.
export const RESERVED_QUERY_PARAMS = new Set([
  "sort",
  "view",
  "per_page",
  "page",
  "q",
  "search",
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_content",
  "utm_term",
  "debug",
]);

// Бренд label → slug (URL латиницей; кириллица в URL не попадает).
export const BRAND_SLUGS: Record<string, string> = {
  Bosch: "bosch",
  Makita: "makita",
  DeWalt: "dewalt",
  Metabo: "metabo",
  Интерскол: "interskol",
};

export const CHUCK_SLUGS: Record<string, string> = {
  "SDS-Plus": "sds-plus",
  "SDS-Max": "sds-max",
};
