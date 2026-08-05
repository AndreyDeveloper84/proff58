import type { ProductSpec } from "@/lib/types";
import { selectKeySpecs } from "./ProductDetailsShowcase";

/**
 * Паспортные чипы под галереей (макет pdp-v4): «800 Вт · 3 Дж · SDS-plus».
 *
 * Зачем дублировать то, что есть в «Главном в работе» ниже: до этого блока надо
 * доскроллить, а решение «мой это инструмент или нет» человек принимает, ещё
 * глядя на фото. Здесь только значения — без подписей, иначе ряд превращается
 * в таблицу и перестаёт читаться одним взглядом.
 */
export function SpecChips({ specs, limit = 4 }: { specs: ProductSpec[]; limit?: number }) {
  const chips = selectKeySpecs(specs, limit).filter((spec) => spec.value.length <= 24);
  if (!chips.length) return null;

  return (
    <ul className="flex flex-wrap gap-2" aria-label="Ключевые характеристики">
      {chips.map((spec) => (
        <li
          key={`${spec.label}-${spec.value}`}
          title={spec.label}
          className="rounded-pill border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink-2"
        >
          {spec.value}
        </li>
      ))}
    </ul>
  );
}
