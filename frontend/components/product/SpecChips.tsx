import type { ProductSpec } from "@/lib/types";
import { keySpecs } from "@/lib/specs";

/**
 * Паспортные чипы под галереей (макет pdp-v4): «800 Вт · 3 Дж · SDS-plus».
 *
 * Зачем дублировать то, что есть в «Главном в работе» ниже: до этого блока надо
 * доскроллить, а решение «мой это инструмент или нет» человек принимает, ещё
 * глядя на фото.
 *
 * DATA-01: у каждого значения есть подпись. Ряд «800 · 3 · 13» без названий
 * покупатели читали как шум — непонятно, что из этого мощность, а что диаметр.
 * Подпись мельче и светлее значения, поэтому ряд по-прежнему читается взглядом.
 * Состав и порядок — общие с карточкой списка и быстрым просмотром (lib/specs).
 */
export function SpecChips({ specs, limit = 4 }: { specs: ProductSpec[]; limit?: number }) {
  const chips = keySpecs(specs, limit).filter((spec) => spec.value.length <= 24);
  if (!chips.length) return null;

  return (
    <ul className="flex flex-wrap gap-2" aria-label="Ключевые характеристики">
      {chips.map((spec) => (
        <li
          key={`${spec.label}-${spec.value}`}
          className="rounded-pill border border-line bg-surface px-3 py-1.5 text-sm text-ink-3"
        >
          {spec.label}: <span className="font-semibold text-ink">{spec.value}</span>
        </li>
      ))}
    </ul>
  );
}
