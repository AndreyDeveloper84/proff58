"use client";

import { useState } from "react";
import Image from "next/image";
import { ChevronDown, ChevronRight } from "lucide-react";

import { toolTypeArtwork } from "@/lib/category-artwork";
import { categoryGenitive, popularTypesTitle } from "@/lib/category-phrases";
import type { CategoryNavItem } from "@/lib/listing";
import { cn } from "@/lib/utils";

// Плитки видов инструмента — вторая ось навигации раздела (DRF-993, макет Cat2).
//
// Раньше здесь был ряд капсул: на «Электроинструменте» это стена из 44 равноправных
// пилюль, которую человек сканирует глазами прежде, чем увидит хоть один товар.
// Плитка крупнее и говорит больше: название, количество товаров и картинка, — но
// главное, что их всего 12, а остальное убрано под кнопку.
//
// Капсулы остались для подкатегорий (CategoryNavStrip): подкатегория — переход на
// другую страницу, а не выбор вида, и разворачивать её в плитку не за чем.

const COLLAPSED_COUNT = 12;

type Props = {
  /** Название раздела — из него строится заголовок «Популярные виды …». */
  categoryTitle: string;
  items: CategoryNavItem[];
  onSelect: (key: string, label: string) => void;
};

function Tile({ item, onSelect }: { item: CategoryNavItem; onSelect: Props["onSelect"] }) {
  const image = toolTypeArtwork(item.key);
  return (
    <button
      type="button"
      aria-pressed={item.active}
      onClick={() => onSelect(item.key, item.label)}
      className={cn(
        // min-h-16: плитка — основная навигация раздела, зона нажатия заведомо выше
        // минимальных 44 px даже без картинки.
        "flex min-h-16 w-full items-center gap-3 rounded-lg border bg-surface px-3 py-2.5 text-left transition",
        item.active
          ? "border-accent bg-accent/5"
          : "border-line hover:border-accent hover:bg-raised",
      )}
    >
      {image && (
        <Image
          src={image}
          alt=""
          width={56}
          height={56}
          className="h-14 w-14 shrink-0 object-contain dark:invert"
        />
      )}
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate text-sm font-semibold", item.active ? "text-accent" : "text-ink")}>
          {item.label}
        </span>
        {item.count != null && (
          <span className="mt-0.5 block text-xs text-ink-3">{item.count}</span>
        )}
      </span>
      <ChevronRight className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
    </button>
  );
}

export function TypeTiles({ categoryTitle, items, onSelect }: Props) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, COLLAPSED_COUNT);
  const hidden = items.length - shown.length;

  return (
    <section className="mb-5">
      <h2 className="mb-3 font-display text-lg font-semibold text-ink">
        {popularTypesTitle(categoryTitle)}
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {shown.map((item) => (
          <Tile key={item.key} item={item} onSelect={onSelect} />
        ))}
      </div>
      {(hidden > 0 || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-line bg-raised text-sm font-medium text-ink-2 transition hover:border-accent hover:text-accent"
        >
          {expanded ? "Свернуть" : allTypesButtonLabel(categoryTitle)}
          <ChevronDown className={cn("h-4 w-4 transition", expanded && "rotate-180")} aria-hidden />
        </button>
      )}
    </section>
  );
}

/** «Показать все виды электроинструмента»; незнакомый раздел — без хвоста. */
function allTypesButtonLabel(categoryTitle: string): string {
  const genitive = categoryGenitive(categoryTitle);
  return genitive ? `Показать все виды ${genitive}` : "Показать все виды";
}
