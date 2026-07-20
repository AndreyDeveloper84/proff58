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
  videoUrl?: string; // ссылка на видео о товаре (YouTube)
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

// Группа технического фасета в сайдбаре (§22.4): «Основные» / «Дополнительные».
export type FacetGroupKind = "main" | "extra";

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
  // Раздел сайдбара (§22.4, D1/D2): main — «Основные»; extra — «Дополнительные» (свёрнуты).
  // Маппится из ApiFacet.group. Осмыслен только для технических (kind:"tech") фасетов;
  // базовые (kind:"base") и навигация (kind:"nav") группируются отдельно. undefined → main.
  group?: FacetGroupKind;
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
    hero?: {
      image: string | null;
      eyebrow: string;
    };
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

// ---------------------------------------------------------------------------
// Корзина и заказ (#246). Формы 1:1 с контрактом DRF apps/orders/api/serializers
// (денежные поля — строки, как их рендерит DecimalField; null при отсутствии цены).
// Доступ из браузера — только через same-origin BFF (app/api/cart*, app/api/orders).
// ---------------------------------------------------------------------------
export type CartLine = {
  id: number;
  product_id: number;
  name: string;
  slug: string;
  quantity: number;
  price_final: string | null;
  price_base: string | null;
  discount: string | null;
  price_type: string;
  currency: string;
  line_total: string | null;
};

export type Cart = {
  id: number;
  status: string;
  lines: CartLine[];
  total: string;
  currency: string;
  // #375: валюты строк различаются → бэк обнуляет total и поднимает флаг.
  // Без обработки флага UI показывал «Итого: 0 ₽» без объяснения причины.
  has_mixed_currencies: boolean;
};

export type OrderItem = {
  id: number;
  product_id: number | null;
  code_1c: string;
  article: string;
  name: string;
  unit: string;
  price_base: string | null;
  price_final: string | null;
  discount: string | null;
  price_type: string;
  currency: string;
  quantity: number;
  line_total: string | null;
};

// Оси статусов заказа — union-литералы значений Django TextChoices
// (apps/orders/models.py). Не расширять «на всякий случай»: расхождение с бэком
// должно падать типами, а не молча уходить в серый бейдж.
// ВНИМАНИЕ: payment_status — ось ЗАКАЗА (orders.PaymentStatus: "paid" = оплачен),
// НЕ статус платежа ЮKassa (payments.PaymentStatus: там "succeeded") — не путать.
export type FulfillmentStatus =
  | "new"
  | "confirmed"
  | "assembling"
  | "ready"
  | "shipped"
  | "completed"
  | "cancelled";
export type OrderPaymentStatus =
  | "pending"
  | "paid"
  | "expired"
  | "partially_refunded"
  | "refunded";
export type Sync1CStatus = "pending" | "exported";

export type Order = {
  id: number;
  order_number: string;
  external_order_id: string;
  fulfillment_status: FulfillmentStatus;
  payment_status: OrderPaymentStatus;
  sync_1c_status: Sync1CStatus;
  // Человекочитаемый статус (display_status бэка) — ТОЛЬКО текст бейджа.
  // Логика (вкладки, счётчики, цвета) — по осям выше, см. lib/order-status.ts.
  display_status: string;
  customer_name: string;
  customer_phone: string;
  customer_email: string;
  customer_type: string;
  company_name: string;
  inn: string;
  kpp: string;
  legal_address: string;
  delivery_method: string;
  delivery_address: string;
  // Серверный расчёт доставки (#429/M-05): зона, стоимость (null = manual_required,
  // менеджер посчитает) и статус расчёта. Decimal → строка.
  delivery_zone: string;
  delivery_cost: string | null;
  delivery_calc_status: string;
  comment: string;
  payment_method: string;
  total: string;
  // Снимок НДС для B2B (#430/M-06): ставка — число, суммы — строки; для B2C нулевые.
  vat_rate: number;
  vat_amount: string;
  amount_without_vat: string;
  currency: string;
  created_at: string;
  items: OrderItem[];
  // Только для гостевых заказов (#322/#520) — сервер отдаёт при создании, если
  // user=None; для зарегистрированных отсутствует. Используется на /thanks для
  // CTA «Отслеживать заказ в MAX» (#520), НЕ пробрасывается дальше на клиент.
  access_token?: string;
};

// Тело POST /api/orders/ (см. CreateOrderSerializer). Цена считается на сервере —
// никакие price-поля не передаём. Пустые опциональные поля бэк примет как "".
export type PlaceOrderData = {
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  customer_type?: string;
  company_name?: string;
  inn?: string;
  kpp?: string;
  legal_address?: string;
  delivery_method: string;
  delivery_address?: string;
  // Слаг зоны доставки (GET /api/delivery/zones). Без него сервер не считает
  // стоимость доставки (not_required, 0 ₽) — итог заказа занижен (аудит №5).
  delivery_zone?: string;
  comment?: string;
  payment_method: string;
};

// Настройки уведомлений (#519, Django apps.notifications.api). max_enabled —
// мастер-переключатель канала MAX; остальные — по категориям. consent_version
// (write-only на бэке) обязателен только при включении marketing_enabled.
export type NotificationPreferences = {
  max_enabled: boolean;
  order_updates_enabled: boolean;
  product_availability_enabled: boolean;
  marketing_enabled: boolean;
  marketing_consent_at: string | null;
  marketing_consent_version: string;
};

export type NotificationPreferencesPatch = Partial<
  Pick<
    NotificationPreferences,
    "max_enabled" | "order_updates_enabled" | "product_availability_enabled" | "marketing_enabled"
  >
> & { consent_version?: string };

// Статус подписки «Сообщить о поступлении» (#517/#519) на конкретный товар.
// null — подписки нет вовсе (ни активной, ни отработанной).
export type AvailabilitySubscriptionStatus = {
  status: "active" | "queued" | "notified" | "cancelled" | null;
};

// Строка истории уведомлений (#515, центр уведомлений — #513 epic). read_at
// null — непрочитано. policy_skip_reason непусто, если доставка была
// пропущена по preferences (уведомление всё равно видно в истории).
export type NotificationItem = {
  id: number;
  event: string;
  category: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  policy_skip_reason: string;
  created_at: string;
  read_at: string | null;
};

// Пагинированный ответ DRF LimitOffsetPagination.
export type PaginatedNotifications = {
  count: number;
  next: string | null;
  previous: string | null;
  results: NotificationItem[];
};
