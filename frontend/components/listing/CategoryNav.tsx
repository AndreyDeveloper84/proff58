"use client";

import { useState } from "react";

import type { CategoryNav as Nav, CategoryNavItem } from "@/lib/listing";
import { cn } from "@/lib/utils";

// Навигация «куда дальше» внутри раздела: подкатегории-ссылки либо типы инструмента
// (§3.1, §13–14). Состав пунктов считает categoryNav() — здесь только представление:
// строка капсул под заголовком раздела, одинаковая на всех ширинах.
//
// Почему не в фильтрах. Подкатегория — переход на другую страницу, а не сужение
// выдачи. В левой колонке под фасетами (и тем более в мобильном drawer'е за
// кнопкой «Фильтры») эта навигация читалась как ещё один фильтр и терялась.
//
// Почему капсулы переносятся, а не листаются вбок. Горизонтальная лента на
// десктопе прячет половину пунктов: полосы прокрутки нет, и человек просто не
// узнаёт, что за краем что-то есть. Поэтому ряд переносится, а длинный список
// сворачивается до COLLAPSED_COUNT с кнопкой «Ещё» — видно, что список неполон.

const COLLAPSED_COUNT = 12;

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

/** Свернуть длинный список, но активный пункт показывать всегда (§13–14). */
function visibleItems(items: CategoryNavItem[], expanded: boolean): CategoryNavItem[] {
  if (expanded || items.length <= COLLAPSED_COUNT) return items;
  const shown = items.slice(0, COLLAPSED_COUNT);
  if (shown.some((item) => item.active)) return shown;
  const active = items.find((item) => item.active);
  return active ? [...shown, active] : shown;
}

export function CategoryNavStrip({ nav, onSelect }: Props) {
  const [expanded, setExpanded] = useState(false);
  const shown = visibleItems(nav.items, expanded);
  const hiddenCount = nav.items.length - shown.length;

  const pillCls = (active: boolean) =>
    cn(
      // min-h-11 на мобильном: это основная навигация, зона нажатия ≥44px (§4).
      // На десктопе капсула ниже — там ряд стоит вплотную к заголовку раздела.
      "inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-full border px-4 text-sm transition lg:min-h-9",
      active
        ? "border-accent bg-accent/10 font-medium text-accent"
        : "border-line bg-surface text-ink-2 hover:border-accent hover:text-accent",
    );

  const item = (entry: CategoryNavItem) =>
    entry.href ? (
      <a key={entry.key} href={entry.href} className={pillCls(entry.active)}>
        <span className="truncate">{entry.label}</span>
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
        <span className="truncate">{entry.label}</span>
        {entry.count != null && <Count value={entry.count} active={entry.active} />}
      </button>
    );

  return (
    <nav aria-label={nav.title} className="mb-4 flex flex-wrap items-center gap-2">
      {shown.map(item)}
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="inline-flex min-h-11 items-center rounded-full border border-dashed border-line px-4 text-sm font-medium text-accent transition hover:border-accent lg:min-h-9"
        >
          Ещё {hiddenCount}
        </button>
      )}
      {expanded && nav.items.length > COLLAPSED_COUNT && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="inline-flex min-h-11 items-center px-2 text-sm font-medium text-accent hover:underline lg:min-h-9"
        >
          Свернуть
        </button>
      )}
    </nav>
  );
}
