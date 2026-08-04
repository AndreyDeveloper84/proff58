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
 *  - широкая категория И тип не выбран → только базовые (kind === "base"), технические скрыты;
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
    return nonNav.filter((f) => f.kind === "base" || f.kind == null);
  }
  return nonNav;
}

/**
 * Убрать границы диапазонов, которые в новой выдаче ничего не отсекают.
 *
 * Границы в URL достались от прошлой выдачи. Выставили «до 15 595 ₽» на одном
 * типе инструмента, переключили тип на «Аппараты сварки пластиковых труб» — там
 * всё дешевле 3 850 ₽, и фильтр не отсекает ничего, но продолжает висеть: чип
 * «Цена: до 15 595 ₽», счётчик «2 фильтра», а ползунок упирается в правый край
 * при подписи «до 5 000» — вид сломанного элемента.
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
