// Контекстный гейтинг технических фильтров (Фаза 2, §3.3–3.4, §6–7).
// Чистые функции поверх уже пришедших фасетов — НЕ дублировать эту логику в компонентах.

import type { Facet, Listing } from "./types";

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
