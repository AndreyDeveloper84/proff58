// Контекстный гейтинг технических фильтров (Фаза 2, §3.3–3.4, §6–7).
// Чистые функции поверх уже пришедших фасетов — НЕ дублировать эту логику в компонентах.

import { humanizeToken } from "./format";
import type { Facet, FacetGroupKind, Listing, ListingQuery } from "./types";

// Каноническая таксономия v2: верхний «Электроинструмент» навигируется второй осью
// tool_type, а не деревом — его дочерние узлы в навигации не показываем.
const TYPE_NAV_ROOT_CATEGORIES = new Set(["elektroinstrument"]);

/** Пункт навигации раздела: ссылка (подкатегория) либо переключатель (тип инструмента). */
export type CategoryNavItem = {
  key: string;
  label: string;
  /** Есть только у типов инструмента — у подкатегорий счётчика API не отдаёт. */
  count?: number;
  /** Есть только у подкатегорий: переход на другую страницу, а не фильтр. */
  href?: string;
  active: boolean;
};

export type CategoryNav = {
  title: string;
  items: CategoryNavItem[];
  /** true — ссылки-подкатегории, false — переключатели tool_type. */
  isNavigation: boolean;
};

/**
 * Единый источник пунктов «куда дальше» для страницы категории (§3.1, §13–14).
 * Приоритет у дерева: если у раздела есть подкатегории — показываем их ссылками и
 * НЕ дублируем типами. Иначе — nav-фасет tool_type: значения уже отсортированы API
 * (value_option.sort_order), порядок стабилен, активный тип наверх не прыгает.
 * Активный тип, «вымытый» прочими фильтрами (§14), добавляем синтетическим пунктом
 * с count=0 — иначе пользователь не увидит, что фильтр применён. Подпись фолбэка —
 * humanizeToken(slug), тот же, что у чипа в ListingShell (N3-консистентность).
 */
export function categoryNav(
  listing: Listing,
  category: string,
  toolType?: string,
): CategoryNav | null {
  if (listing.subcategories.length > 0 && !TYPE_NAV_ROOT_CATEGORIES.has(category)) {
    return {
      title: "Разделы",
      isNavigation: true,
      items: listing.subcategories.map((s) => ({
        key: s.href,
        label: s.label,
        href: s.href,
        active: false,
      })),
    };
  }

  const nav = listing.facets.find((f) => f.isNav);
  const items: CategoryNavItem[] = (nav?.options ?? []).map((o) => ({
    key: o.value,
    label: o.label,
    count: o.count,
    active: o.value === toolType,
  }));
  if (toolType != null && !items.some((i) => i.active)) {
    items.push({ key: toolType, label: humanizeToken(toolType), count: 0, active: true });
  }
  if (items.length === 0) return null;

  return { title: nav?.label ?? "Тип инструмента", isNavigation: false, items };
}

/**
 * Панель типов инструмента показывается не всегда (DRF-992).
 *
 * Механизм `tool_type` задумывался навигацией, но на 86 конечных страницах из 158
 * он ничего не навигирует: на 56 из них тип ровно один, ещё на 30 один тип занимает
 * 90 % и больше. «Домкраты → Домкраты» — не выбор, а лишний экран перед товаром.
 *
 * Правила (срез стенда 09.08.2026, см. DRF-991):
 *   A. пунктов ≤ 1                     → панели нет;
 *   B. доля крупнейшего типа ≥ 90 %    → панели нет;
 *   C. пунктов ≥ 2 и доля < 90 %       → показываем;
 *   D. тип уже выбран                  → панели нет (возврат к списку даёт Блок 3).
 *
 * Порог и доля считаются по-разному намеренно. Долю берём по ПОЛНОМУ набору, а порог
 * `count >= 3` применяем после: иначе «Домкраты 79 + Вороток 1» после отсечения хвоста
 * превратились бы в моно-тип, и правило перестало бы быть предсказуемым — один и тот же
 * результат по двум разным причинам. Товары отсечённых типов из выдачи не исчезают:
 * прячется пункт навигации, а не товар.
 */
const TYPE_NAV_MIN_COUNT = 3;
const TYPE_NAV_DOMINANT_SHARE = 0.9;

/**
 * Пункты панели типов либо null, если показывать её не надо.
 *
 * Подкатегории проходят насквозь: приоритет дерева правила A–D не касаются —
 * ссылка на раздел это переход, а не фильтр.
 */
export function typeNavPanel(nav: CategoryNav | null, toolType?: string): CategoryNav | null {
  if (!nav) return null;
  if (nav.isNavigation) return nav;
  if (toolType) return null; // D

  const counted = nav.items.filter((i) => (i.count ?? 0) > 0);
  if (counted.length <= 1) return null; // A
  const total = counted.reduce((sum, i) => sum + (i.count ?? 0), 0);
  const top = Math.max(...counted.map((i) => i.count ?? 0));
  if (total > 0 && top / total >= TYPE_NAV_DOMINANT_SHARE) return null; // B

  // Активный пункт порогу не подчиняется: по прямой ссылке можно прийти в редкий тип,
  // и человек должен видеть, что фильтр применён. Сейчас до этого не доходит (правило D
  // уже вернуло null), но правило живёт вместе с пунктом, а не отдельно от него.
  const visible = counted.filter((i) => (i.count ?? 0) >= TYPE_NAV_MIN_COUNT || i.active);
  // Панель из одной плитки бессмысленна ровно так же, как по правилу A: «10 / 2 / 2»
  // проходит проверку доли (71 %), но после отсечения хвоста выбора не остаётся.
  if (visible.length <= 1) return null;

  // Бэк сортирует по value_option.sort_order — это порядок манифеста таксономии, а не
  // популярность: при обрезке до 12 «Дрели и шуруповёрты» (337 товаров) уезжали под «Ещё».
  const items = [...visible].sort(
    (a, b) => (b.count ?? 0) - (a.count ?? 0) || a.label.localeCompare(b.label, "ru"),
  );
  return { ...nav, items };
}

/**
 * Широкая ли категория (§3.4). Источник режима — поле API `category_filter_mode`
 * (`listing.filterMode`), если задано. Иначе авто-определение: категория широкая ⇔
 * nav-фасет tool_type содержит БОЛЕЕ ОДНОГО значения с count > 0.
 *
 * Нет nav-фасета или ровно один тип с count>0 → НЕ широкая: трактуем как листовую/
 * типизированную (один доминирующий тип), т.е. показываем полный набор фильтров сразу (§6).
 */
export function isBroadCategory(listing: Listing): boolean {
  if (listing.filterMode) return listing.filterMode === "broad";
  const nav = listing.facets.find((f) => f.isNav);
  const typesWithItems = (nav?.options ?? []).filter((o) => o.count > 0).length;
  return typesWithItems > 1;
}

/**
 * Фасеты для левого сайдбара с учётом контекстного гейтинга (§6):
 *  - широкая категория И тип не выбран → базовые (kind === "base") плюс те технические,
 *    что покрывают заметную часть выдачи (см. coversEnough) — остальные скрыты;
 *  - выбран tool_type ИЛИ листовая/типизированная → все пришедшие не-nav фасеты
 *    (drill-down на бэке уже отсёк пустые).
 * nav-фасет (tool_type) исключаем всегда — он рендерится отдельным блоком навигации
 * (categoryNav → CategoryNavStrip), а не рядовым фасетом сайдбара.
 */
export function sidebarFacets(listing: Listing, toolType?: string): Facet[] {
  const nonNav = listing.facets.filter((f) => !f.isNav);
  if (isBroadCategory(listing) && !toolType) {
    // kind == null (фикстуры / неожиданная форма) трактуем как видимый — деградация к
    // «показать базовое», а не к пустому сайдбару. На API-пути kind всегда проставлен.
    return nonNav.filter(
      (f) => f.kind === "base" || f.kind == null || coversEnough(f, listing.total),
    );
  }
  return nonNav;
}

/**
 * Доля выдачи, которую должна покрывать характеристика, чтобы попасть в сайдбар
 * широкой категории (DRF-995, решение по открытому вопросу DRF-991 §5).
 *
 * Полный гейтинг («на широкой категории только базовые фасеты») прятал и то, что
 * осмысленно для раздела целиком: мощность есть у трети электроинструмента. Полное
 * его снятие вернуло бы в сайдбар «Энергию удара», которая относится к 131 товару
 * из 1 518 и для остальных 90 % раздела означает «скрыть всё».
 */
const TECH_FACET_MIN_SHARE = 0.25;

/**
 * Покрывает ли характеристика заметную часть выдачи.
 *
 * Считаем по `covered` из адаптера, а не по options: у диапазонных фасетов значения
 * схлопнуты в min/max, и счётчиков там уже нет. Именно на этом «Мощность» (треть
 * электроинструмента) сначала не попала в сайдбар — она decimal.
 */
function coversEnough(facet: Facet, total: number): boolean {
  if (facet.kind !== "tech" || total <= 0) return false;
  const covered =
    facet.covered ?? (facet.options ?? []).reduce((sum, o) => sum + (o.count ?? 0), 0);
  return covered / total >= TECH_FACET_MIN_SHARE;
}

/**
 * Убрать границы диапазонов, которые в новой выдаче ничего не отсекают.
 *
 * Границы в URL достались от прошлой выдачи: «до 15 595 ₽» на выдаче, где всё
 * дешевле 3 850 ₽, ничего не отсекает, но продолжает висеть — чип «Цена: до
 * 15 595 ₽», счётчик «2 фильтра», ползунок упёрт в правый край. Вид сломанного
 * элемента.
 *
 * Свой тип инструмента такую границу больше не приносит — её сбрасывает
 * filtersAfterToolTypeChange. Здесь остаётся всё, что пришло со стороны: ссылка
 * из письма, чужой поисковой выдачи, сохранённая закладка.
 *
 * Правила ровно те же, которыми фильтр применяется (RangeFacet.commit): граница
 * ниже минимума выдачи или выше её максимума — это «границы нет». Границы,
 * которые реально сужают выдачу — пусть даже до нуля товаров, — не трогаем: за
 * них отвечает пустое состояние с точечным сбросом, молча править выбор
 * человека нельзя. Фасеты диапазонов считаются на бэке без своей же оси
 * (drill-down own-axis), поэтому чистка устойчива: повторный проход уже ничего
 * не меняет.
 *
 * @returns новый набор фильтров либо null, если менять нечего.
 */
export function normalizeRangeFilters(
  filters: ListingQuery["filters"],
  facets: Facet[],
): ListingQuery["filters"] | null {
  let changed = false;
  const next: ListingQuery["filters"] = {};

  for (const [code, val] of Object.entries(filters)) {
    if (Array.isArray(val)) {
      next[code] = val;
      continue;
    }
    const facet = facets.find((f) => f.code === code);
    const lo = facet?.min;
    const hi = facet?.max;
    // Фасета в выдаче нет (не относится к типу) или он без границ (выдача пуста) —
    // судить не о чем, оставляем как есть.
    if (lo == null || hi == null || lo >= hi) {
      next[code] = val;
      continue;
    }
    const min = val.min != null && val.min > lo ? val.min : undefined;
    const max = val.max != null && val.max < hi ? val.max : undefined;
    if (min === val.min && max === val.max) {
      next[code] = val;
      continue;
    }
    changed = true;
    if (min != null || max != null) next[code] = { min, max };
  }

  return changed ? next : null;
}

/**
 * Фильтры, переживающие смену типа инструмента.
 *
 * Бренд и наличие не привязаны к типу: «Bosch, только что есть на складе» —
 * осмысленный отбор и для болгарки, и для перфоратора, и человек задаёт его как
 * общее предпочтение, а не как свойство раздела.
 */
const CROSS_TYPE_FILTERS = new Set(["brand", "stock"]);

/**
 * Фильтры для новой выдачи после смены типа инструмента.
 *
 * Тип — не сужение прежней выборки, а другой список товаров: у болгарки шкала
 * цен 1 600–13 100 ₽ и диаметр диска, у перфоратора — свои цены и патрон.
 * Перенос сюда прежних цены и характеристик выглядел как поломка: покупатель
 * открывает раздел, которого не фильтровал, а там уже стоит «до 15 595 ₽»,
 * висит чип и обрезана выдача.
 *
 * Сбрасываем цену и характеристики (`attr_*`), сохраняем сквозные (бренд,
 * наличие). Снятие типа — та же смена выдачи, правило одно и то же.
 */
export function filtersAfterToolTypeChange(
  filters: ListingQuery["filters"],
): ListingQuery["filters"] {
  const next: ListingQuery["filters"] = {};
  for (const [code, val] of Object.entries(filters)) {
    if (CROSS_TYPE_FILTERS.has(code)) next[code] = val;
  }
  return next;
}

// Секция сайдбара (D2, §22.4): «Базовые» / «Основные» / «Дополнительные». extra-секция
// сворачивается в UI; ключ нужен компоненту для выбора оформления (collapsible).
export type FacetSectionKey = "base" | FacetGroupKind;
export type FacetSection = { key: FacetSectionKey; label: string; facets: Facet[] };

const SECTION_LABEL: Record<FacetSectionKey, string> = {
  base: "Базовые",
  main: "Основные",
  extra: "Дополнительные",
};

/**
 * Разложить фасеты сайдбара по группам (§22.4) для рендера секциями (D2). Порядок секций
 * фиксирован: Базовые → Основные → Дополнительные. Пустые секции опускаются.
 *  - «Базовые» — kind === "base" (бренд/наличие/цена/тип питания), а также неклассифицированные
 *    (kind == null) — деградация к видимой базовой секции, а не к их потере;
 *  - «Основные» — технические с group !== "extra" (дефолт);
 *  - «Дополнительные» — технические с group === "extra" (свёрнуты в UI).
 * nav-фасет сюда не попадает — его отсекает sidebarFacets выше; на всякий
 * случай исключаем kind === "nav" повторно (вход может прийти не через sidebarFacets).
 */
export function groupSidebarFacets(facets: Facet[]): FacetSection[] {
  const visible = facets.filter((f) => f.kind !== "nav" && !f.isNav);
  const base = visible.filter((f) => f.kind === "base" || f.kind == null);
  const tech = visible.filter((f) => f.kind === "tech");
  const buckets: Record<FacetSectionKey, Facet[]> = {
    base,
    main: tech.filter((f) => f.group !== "extra"),
    extra: tech.filter((f) => f.group === "extra"),
  };
  const order: FacetSectionKey[] = ["base", "main", "extra"];
  return order
    .filter((key) => buckets[key].length > 0)
    .map((key) => ({ key, label: SECTION_LABEL[key], facets: buckets[key] }));
}

/**
 * Пресеты цены под слайдером (DRF-995, макет Cat2).
 *
 * Готовые диапазоны отвечают на «сколько я готов потратить» быстрее, чем два поля
 * и бегунок. Но показывать все четыре всегда нельзя: «от 15 000 ₽» на выдаче, где
 * самый дорогой товар стоит 12 000, — это кнопка, дающая ноль товаров. Такие же
 * пресеты, которые не отсекают ничего (нижняя граница ниже минимума выдачи, верхняя
 * выше максимума), молча вычистит normalizeRangeFilters — нажатие выглядело бы как
 * «ничего не произошло». И то и другое отсеиваем здесь.
 */
export type PricePreset = { label: string; min?: number; max?: number };

const PRICE_PRESETS: PricePreset[] = [
  { label: "до 3 000", max: 3000 },
  { label: "3 000 – 7 000", min: 3000, max: 7000 },
  { label: "7 000 – 15 000", min: 7000, max: 15000 },
  { label: "от 15 000", min: 15000 },
];

/** Пресеты, осмысленные для текущей шкалы цен: пересекают её и реально сужают. */
export function pricePresets(lo?: number, hi?: number): PricePreset[] {
  if (lo == null || hi == null || lo >= hi) return [];
  return PRICE_PRESETS.filter((preset) => {
    const from = preset.min ?? lo;
    const to = preset.max ?? hi;
    if (from >= hi || to <= lo) return false; // за пределами шкалы — ноль товаров
    return from > lo || to < hi; // не сужает ничего — фильтр всё равно будет сброшен
  });
}
