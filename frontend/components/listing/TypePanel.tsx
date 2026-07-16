"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { humanizeToken } from "@/lib/format";
import type { Facet, FacetOption } from "@/lib/types";

// TypePanel — НАВИГАЦИЯ по типу инструмента (панель кнопок над выдачей), §3.1, §13–14.
// Источник — nav-фасет (isNav) из listing.facets: его значения уже отсортированы API
// (value_option.sort_order) и несут count/selected. Это НЕ сайдбар-фасет: выбор уходит
// верхнеуровневым ?tool_type=<slug>, тоггл решает родитель (ListingShell).

type Props = {
  facet?: Facet; // nav-фасет (isNav); если его нет — панель не рендерится
  active?: string; // активный tool_type (slug) из query.toolType
  onSelect: (slug: string, label: string) => void; // клик по плитке (toggle решает родитель)
};

const INITIAL_VISIBLE_TYPES = 12;

export function TypePanel({ facet, active, onSelect }: Props) {
  const [expanded, setExpanded] = useState(false);
  if (!facet) return null;
  const options = facet.options ?? [];

  // §13–14: порядок стабилен (как из API), активный тип НЕ прыгает наверх. До фильтров
  // типы с count=0 API не присылает; после — активный тип виден всегда, даже при 0:
  // если он отсутствует в выдаче, добавляем синтетическую плитку в конец. Подпись —
  // humanizeToken(slug) (тот же фолбэк, что и для чипа в ListingShell — N3-консистентность).
  const tiles: FacetOption[] = [...options];
  if (active != null && !tiles.some((o) => o.value === active)) {
    tiles.push({ value: active, label: humanizeToken(active), count: 0, selected: true });
  }
  if (tiles.length === 0) return null;

  const visibleTiles = expanded ? tiles : tiles.slice(0, INITIAL_VISIBLE_TYPES);
  if (
    !expanded &&
    active != null &&
    !visibleTiles.some((o) => o.value === active)
  ) {
    const activeTile = tiles.find((o) => o.value === active);
    if (activeTile) visibleTiles.push(activeTile);
  }
  const hiddenCount = Math.max(0, tiles.length - INITIAL_VISIBLE_TYPES);

  return (
    <nav aria-label="Тип инструмента" className="mb-4">
      <div className="flex flex-wrap gap-2">
        {visibleTiles.map((o) => {
          const isActive = o.value === active;
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={isActive}
              onClick={() => onSelect(o.value, o.label)}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition",
                isActive
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-line bg-surface text-ink-2 hover:border-accent hover:text-accent",
              )}
            >
              <span className="font-medium">{o.label}</span>
              <span
                className={cn(
                  "rounded-full px-1.5 text-xs",
                  isActive ? "bg-accent/20 text-accent" : "bg-raised text-ink-3",
                )}
              >
                {o.count}
              </span>
            </button>
          );
        })}
      </div>

      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className="mt-3 min-h-11 text-sm font-semibold text-accent hover:underline sm:min-h-0"
        >
          {expanded ? "Свернуть типы" : `Показать ещё (${hiddenCount})`}
        </button>
      )}
    </nav>
  );
}
