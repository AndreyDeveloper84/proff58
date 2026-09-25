import { keySpecs } from "@/lib/specs";
import type { ProductSpec } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Ключевые характеристики в карточке списка (DATA-01).
 *
 * Раньше здесь была одна строка значений через «·» — «Да · 505 мм · 76 шт.»: что
 * означает каждое число, понять было нельзя, а длинная строка обрезалась. Теперь это
 * пары «Название: значение», по одной на строку. Порядок и состав — с backend (по
 * типу товара), служебный «Тип инструмента» не показываем.
 *
 * Нет характеристик — компонент ничего не рисует: пустых строк и выдуманных
 * значений в карточке быть не должно.
 */
export function ProductSpecs({
  specs,
  limit = 3,
  className,
}: {
  specs: ProductSpec[];
  limit?: number;
  className?: string;
}) {
  const rows = keySpecs(specs, limit);
  if (!rows.length) return null;
  return (
    <dl className={cn("space-y-0.5 text-xs leading-snug text-ink-3", className)}>
      {rows.map((spec) => (
        <div key={`${spec.slug ?? spec.label}`} className="flex gap-1">
          <dt className="shrink-0">{spec.label}:</dt>
          {/* truncate у значения, а не у строки: подпись остаётся целой всегда. */}
          <dd className="min-w-0 truncate font-medium text-ink-2" title={spec.value}>
            {spec.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
