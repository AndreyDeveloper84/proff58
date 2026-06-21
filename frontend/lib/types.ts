// Формы данных витрины — повторяют будущий ответ каталога (DRF), чтобы переход
// на /api/catalog/... был заменой реализации getListing(), а не переверсткой.

export type StockState = "in" | "order" | "out";
export type BadgeKind = "hit" | "new" | "sale";
export type ProductSpec = { label: string; value: string };

export type Product = {
  id: number;
  slug: string;
  name: string;
  brand: string;
  image?: string;
  rating?: number;
  reviews?: number;
  specs: ProductSpec[];
  energy?: string; // спек-чип/signature (энергия удара, Дж)
  power?: string; // мощность, Вт
  chuck?: string; // тип патрона
  price: { final?: number; old?: number; discountPct?: number; currency: "RUB" };
  stock: StockState;
  stockQty?: number;
  badges: BadgeKind[];
};

export type FacetOption = {
  value: string;
  label: string;
  count: number;
  selected: boolean;
};
export type Facet = {
  code: string;
  label: string;
  type: "range" | "checkbox" | "slider";
  options?: FacetOption[];
  min?: number;
  max?: number;
  unit?: string;
};

export type SortOption = "popular" | "price_asc" | "price_desc" | "new" | "rating";
export type RangeFilterValue = { min?: number; max?: number };

export type ListingQuery = {
  category: string;
  page: number;
  perPage: number;
  sort: SortOption;
  view: "grid" | "list";
  filters: Record<string, string[] | RangeFilterValue>;
};

export type Listing = {
  category: {
    title: string;
    intro: string;
    breadcrumb: { label: string; href: string }[];
  };
  promo?: { title: string; subtitle: string; href: string };
  subcategories: { label: string; href: string }[];
  facets: Facet[];
  sort: { value: SortOption; label: string }[];
  total: number;
  page: number;
  perPage: number;
  products: Product[];
};
