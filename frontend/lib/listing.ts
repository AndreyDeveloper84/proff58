// Контекстный гейтинг технических фильтров (Фаза 2, §3.3–3.4, §6–7).
// Чистые функции поверх уже пришедших фасетов — НЕ дублировать эту логику в компонентах.

import type { Facet, FacetGroupKind, Listing } from "./types";

/**
 * Широкая ли категория (§3.4). Источник режима — поле API `category_filter_mode`
 * (`listing.filterMode`), если задано. Иначе авто-определение: категория широкая ⇔
 * TypePanel (nav-фасет tool_type) содержит БОЛЕЕ ОДНОГО значения с count > 0.
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
 * nav-фасет (tool_type) исключаем всегда — он рендерится TypePanel над выдачей.
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
 * nav-фасет (TypePanel) сюда не попадает — его отсекает sidebarFacets выше; на всякий
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
