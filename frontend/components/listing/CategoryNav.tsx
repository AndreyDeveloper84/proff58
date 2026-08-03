"use client";

import type { CategoryNav as Nav, CategoryNavItem } from "@/lib/listing";
import { cn } from "@/lib/utils";

// Навигация «куда дальше» внутри раздела: подкатегории-ссылки либо типы инструмента
// (§3.1, §13–14). Состав пунктов считает categoryNav() — здесь только представление:
// строка капсул под заголовком раздела, одинаковая на всех ширинах.
//
// Почему не в фильтрах. Подкатегория — переход на другую страницу, а не сужение
// выдачи. В левой колонке под фасетами (и тем более в мобильном drawer'е за
// кнопкой «Фильтры») эта навигация читалась как ещё один фильтр и терялась.
// Типы инструмента держим рядом с ней, чтобы разделы вели себя одинаково.

type Props = {
  nav: Nav;
  /** Клик по переключателю типа; для подкатегорий не вызывается — там обычная ссылка. */
  onSelect: (key: string, label: string) => void;
};

function Count({ value, active }: { value: number; active: boolean }) {
  return (
    <span className={cn("shrink-0 text-xs", active ? "text-accent" : "text-ink-3")}>{value}</span>
  );
}

export function CategoryNavStrip({ nav, onSelect }: Props) {
  const pillCls = (active: boolean) =>
    cn(
      // min-h-11 на мобильном: это основная навигация, зона нажатия ≥44px (§4).
      // На десктопе капсула ниже — там ряд стоит вплотную к заголовку раздела.
      "inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-4 text-sm transition lg:min-h-9",
      active
        ? "border-accent bg-accent/10 font-medium text-accent"
        : "border-line bg-surface text-ink-2 hover:border-accent hover:text-accent",
    );

  const item = (entry: CategoryNavItem) =>
    entry.href ? (
      <a key={entry.key} href={entry.href} className={pillCls(entry.active)}>
        {entry.label}
        {entry.count != null && <Count value={entry.count} active={entry.active} />}
      </a>
    ) : (
      <button
        key={entry.key}
        type="button"
        aria-pressed={entry.active}
        onClick={() => onSelect(entry.key, entry.label)}
        className={pillCls(entry.active)}
      >
        {entry.label}
        {entry.count != null && <Count value={entry.count} active={entry.active} />}
      </button>
    );

  return (
    <nav aria-label={nav.title} className="mt-3">
      {/* Одна строка со свайпом: отрицательный отступ уводит скролл под края
          контейнера, чтобы обрезанная капсула читалась как «листается дальше». */}
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] lg:-mx-1 lg:px-1 [&::-webkit-scrollbar]:hidden">
        {nav.items.map(item)}
      </div>
    </nav>
  );
}
