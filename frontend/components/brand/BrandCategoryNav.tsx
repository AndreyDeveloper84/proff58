"use client";

import Link, { useLinkStatus } from "next/link";
import type { BrandCategory } from "@/lib/adapters";
import { cn } from "@/lib/utils";

// Индикатор перехода внутри самой ссылки: страница бренда динамическая, и без него
// клик по категории ничего не показывает, пока сервер не ответит (PERF-01).
function Pending() {
  const { pending } = useLinkStatus();
  return (
    <span
      aria-hidden
      className={cn(
        "h-1.5 w-1.5 shrink-0 rounded-full bg-current transition-opacity",
        pending ? "animate-pulse opacity-100" : "opacity-0",
      )}
    />
  );
}

/**
 * Категории бренда (UX-07): выбор сужает выдачу ВНУТРИ бренда, сам бренд остаётся в
 * пути. Ссылки, а не кнопки: категорию можно открыть в новой вкладке и переслать.
 * `hrefFor` строит страница — она знает остальные параметры URL (сортировку, фильтры),
 * которые выбор категории обязан сохранить; страница сбрасывается на первую.
 */
export function BrandCategoryNav({
  categories,
  allHref,
  hrefs,
  brandTotal,
}: {
  categories: BrandCategory[];
  allHref: string;
  hrefs: Record<string, string>;
  brandTotal: number;
}) {
  if (categories.length === 0) return null;
  const anySelected = categories.some((c) => c.selected);
  const chip =
    "inline-flex min-h-11 items-center gap-2 rounded-full border px-4 text-sm transition sm:min-h-10";
  const on = "border-accent bg-accent/10 font-semibold text-accent";
  const off = "border-line bg-surface text-ink-2 hover:border-accent hover:text-accent";

  return (
    <nav aria-label="Категории бренда" className="mt-4">
      <ul className="flex flex-wrap gap-2">
        <li>
          <Link
            href={allHref}
            scroll={false}
            aria-current={anySelected ? undefined : "true"}
            className={cn(chip, anySelected ? off : on)}
          >
            Все товары
            <span className="text-xs text-ink-3">{brandTotal}</span>
            <Pending />
          </Link>
        </li>
        {categories.map((category) => (
          <li key={category.slug}>
            <Link
              href={hrefs[category.slug] ?? allHref}
              scroll={false}
              aria-current={category.selected ? "true" : undefined}
              className={cn(chip, category.selected ? on : off)}
            >
              {category.name}
              <span className="text-xs text-ink-3">{category.count}</span>
              <Pending />
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
