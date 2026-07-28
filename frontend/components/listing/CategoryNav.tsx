"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import type { CategoryNav as Nav, CategoryNavItem } from "@/lib/listing";
import { cn } from "@/lib/utils";

// Навигация «куда дальше» внутри раздела: подкатегории-ссылки либо типы инструмента
// (§3.1, §13–14). Состав пунктов считает categoryNav() — здесь только представление,
// два варианта под ширину экрана:
//   CategoryNavPanel — вертикальный сворачиваемый блок левой колонки (lg+), над фильтрами;
//   CategoryNavStrip — одна строка со свайпом на мобильном.
// Почему не в drawer фильтров: подкатегория — переход на другую страницу, прятать
// навигацию за кнопкой «Фильтры» нельзя. Типы держим рядом с ними, чтобы страницы
// каталога вели себя одинаково.

const COLLAPSED_COUNT = 8;

type Props = {
  nav: Nav;
  /** Клик по переключателю типа; для подкатегорий не вызывается — там обычная ссылка. */
  onSelect: (key: string, label: string) => void;
};

/** Свернуть длинный список, но активный пункт показывать всегда (§13–14). */
function useVisibleItems(items: CategoryNavItem[], limit: number) {
  const [expanded, setExpanded] = useState(false);
  const hiddenCount = Math.max(0, items.length - limit);
  const visible = expanded ? items : items.slice(0, limit);
  if (!expanded && !visible.some((i) => i.active)) {
    const active = items.find((i) => i.active);
    if (active) visible.push(active);
  }
  return { visible, hiddenCount, expanded, setExpanded };
}

function Count({ value, active }: { value: number; active: boolean }) {
  return (
    <span className={cn("shrink-0 text-xs", active ? "text-accent" : "text-ink-3")}>{value}</span>
  );
}

export function CategoryNavPanel({ nav, onSelect }: Props) {
  const { visible, hiddenCount, expanded, setExpanded } = useVisibleItems(
    nav.items,
    COLLAPSED_COUNT,
  );

  const itemCls = (active: boolean) =>
    cn(
      "flex min-h-9 w-full items-center gap-2 rounded-md px-2 -mx-2 text-left text-sm transition",
      active
        ? "bg-accent/10 font-semibold text-accent"
        : "text-ink-2 hover:bg-raised hover:text-accent",
    );

  return (
    <nav aria-label={nav.title} className="rounded-lg border border-line bg-surface p-4">
      <details open className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold text-ink">
          {nav.title}
          <ChevronDown
            className="h-4 w-4 text-ink-3 transition group-open:rotate-180"
            aria-hidden
          />
        </summary>

        <ul className="mt-3 flex flex-col">
          {visible.map((item) => (
            <li key={item.key}>
              {item.href ? (
                <a href={item.href} className={itemCls(item.active)}>
                  <span className="min-w-0 flex-1">{item.label}</span>
                  {item.count != null && <Count value={item.count} active={item.active} />}
                </a>
              ) : (
                <button
                  type="button"
                  aria-pressed={item.active}
                  onClick={() => onSelect(item.key, item.label)}
                  className={itemCls(item.active)}
                >
                  <span className="min-w-0 flex-1">{item.label}</span>
                  {item.count != null && <Count value={item.count} active={item.active} />}
                </button>
              )}
            </li>
          ))}
        </ul>

        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            className="mt-2 text-sm font-medium text-accent hover:underline"
          >
            {expanded ? "Свернуть" : `Показать ещё (${hiddenCount})`}
          </button>
        )}
      </details>
    </nav>
  );
}

export function CategoryNavStrip({ nav, onSelect }: Props) {
  const pillCls = (active: boolean) =>
    cn(
      // min-h-11: на мобильном это основная навигация — зона нажатия ≥44px (§4).
      "inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-4 text-sm transition",
      active
        ? "border-accent bg-accent/10 font-medium text-accent"
        : "border-line bg-surface text-ink-2",
    );

  return (
    <nav aria-label={nav.title} className="mb-4 lg:hidden">
      {/* Одна строка со свайпом: отрицательный отступ уводит скролл под края
          контейнера, чтобы обрезанная пилюля читалась как «листается дальше». */}
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {nav.items.map((item) =>
          item.href ? (
            <a key={item.key} href={item.href} className={pillCls(item.active)}>
              {item.label}
            </a>
          ) : (
            <button
              key={item.key}
              type="button"
              aria-pressed={item.active}
              onClick={() => onSelect(item.key, item.label)}
              className={pillCls(item.active)}
            >
              {item.label}
              {item.count != null && <Count value={item.count} active={item.active} />}
            </button>
          ),
        )}
      </div>
    </nav>
  );
}
