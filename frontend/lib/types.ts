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

// Изображение товара для галереи карточки (PDP). isMain — главное фото (показываем первым).
export type ProductImageData = { url: string; alt: string; isMain: boolean };

// Секции совместимости карточки товара (бэк: /products/{slug}/compatible/).
export type CompatibilitySections = {
  accessories: Product[]; // аксессуары/оснастка К товару
  fits: Product[]; // к чему подходит (для аксессуара)
  compatible: Product[]; // симметрично совместимые
};

// Полные данные карточки товара (PDP): Product + поля detail-эндпоинта.
export type ProductDetail = Product & {
  images: ProductImageData[];
  description: string;
  breadcrumb: { name: string; slug: string }[]; // категории от корня (без «Главная/Каталог»)
  compatible?: CompatibilitySections;
};

export type FacetOption = {
  value: string;
  label: string;
  count: number;
  selected: boolean;
};

// Класс фасета для контекстного гейтинга (§3.3–3.4, §6): nav — TypePanel над выдачей;
// base — базовые фильтры (Наличие/Бренд/Цена/Тип питания), видны всегда; tech — технические,
// видны только после выбора tool_type или на листовой/типизированной категории.
export type FacetKind = "nav" | "base" | "tech";

export type Facet = {
  code: string;
  label: string;
  type: "range" | "checkbox" | "slider";
  options?: FacetOption[];
  min?: number;
  max?: number;
  unit?: string;
  // Навигационный фасет (tool_type): рендерится TypePanel над выдачей, а НЕ в сайдбаре.
  // Маппится из ApiFacet.is_nav. Выбор идёт верхнеуровневым ?tool_type=, не attr_*.
  isNav?: boolean;
  // Класс для гейтинга сайдбара (классифицируется в adapters при маппинге).
  kind?: FacetKind;
};

export type SortOption = "popular" | "price_asc" | "price_desc" | "new" | "rating";
export type RangeFilterValue = { min?: number; max?: number };

// Режим показа фильтров категории (§3.4): broad — широкая (только базовые до выбора типа);
// typed — доминирует один тип; leaf — листовая (полный набор сразу). Источник — поле API
// category_filter_mode, если есть; иначе авто-определение по TypePanel (см. lib/listing.ts).
export type FilterMode = "broad" | "typed" | "leaf";

export type ListingQuery = {
  category: string;
  page: number;
  perPage: number;
  sort: SortOption;
  view: "grid" | "list";
  // tool_type — НАВИГАЦИЯ (панель типов над выдачей), верхнеуровневый ?tool_type=<slug>.
  // Хранится отдельно от filters: это не сайдбар-фасет и не attr_* (§3.1, §5.1).
  toolType?: string;
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
  // Режим гейтинга фильтров (§3.4). undefined → авто-определение по TypePanel (lib/listing.ts).
  filterMode?: FilterMode;
  facets: Facet[];
  sort: { value: SortOption; label: string }[];
  total: number;
  page: number;
  perPage: number;
  products: Product[];
};
