// Ключевые характеристики товара — единый отбор для карточки списка, быстрого
// просмотра и страницы товара (DATA-01).
//
// Порядок задаёт backend (apps/catalog/attribute_display.py: по типу товара, а не по
// алфавиту), поэтому здесь НИЧЕГО не пересортировывается: витрина берёт первые N и
// этим гарантирует, что три места показывают одно и то же в одном порядке.
import type { ProductSpec } from "./types";

const TOOL_TYPE_SLUG = "tool_type";

/**
 * Тип инструмента — служебная строка разбора каталога: она дублирует название и
 * раздел, а у 12 тысяч товаров это вообще единственная «характеристика».
 * Сверяем по slug; подпись — запасной признак для данных без slug (фикстуры).
 */
export function isToolTypeSpec(spec: ProductSpec): boolean {
  return spec.slug === TOOL_TYPE_SLUG || /^тип инструмента$/i.test(spec.label.trim());
}

/** Есть ли у товара хоть одна настоящая характеристика. */
export function hasRealSpecs(specs: ProductSpec[] | undefined): boolean {
  return (specs ?? []).some((spec) => spec.value !== "" && !isToolTypeSpec(spec));
}

/**
 * Первые `limit` ключевых характеристик в порядке backend.
 *
 * `isKey` приходит только из detail-эндпоинта (там отдаются ВСЕ характеристики, и
 * нужно отличать ключевые); list-эндпоинт отдаёт уже только ключевые и флага не шлёт —
 * отсутствие флага значит «ключевая».
 */
export function keySpecs(specs: ProductSpec[] | undefined, limit: number): ProductSpec[] {
  return (specs ?? [])
    .filter((spec) => spec.value !== "" && spec.isKey !== false && !isToolTypeSpec(spec))
    .slice(0, limit);
}
