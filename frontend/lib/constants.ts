import type { SortOption } from "./types";

export const PER_PAGE_OPTIONS = [12, 24, 48] as const;
export const DEFAULT_PER_PAGE = 24;
export const DEFAULT_SORT: SortOption = "popular";

export const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "popular", label: "Популярные" },
  { value: "price_asc", label: "Сначала дешёвые" },
  { value: "price_desc", label: "Сначала дорогие" },
  { value: "new", label: "Новинки" },
  { value: "rating", label: "По рейтингу" },
];

// Диапазонные фасеты — в URL как code_min / code_max.
export const RANGE_FACETS = ["price", "energy_impact"] as const;
// Чекбокс-фасеты — в URL как code=val1,val2.
export const CHECKBOX_FACETS = ["brand", "stock", "chuck"] as const;

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
