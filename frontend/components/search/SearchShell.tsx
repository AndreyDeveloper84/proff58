"use client";

import { useCallback, useRef, useState, useTransition } from "react";
import { usePathname, useRouter } from "next/navigation";
import { SlidersHorizontal } from "lucide-react";
import { FacetSidebar } from "@/components/filters/FacetSidebar";
import { MobileFilterDrawer } from "@/components/listing/MobileFilterDrawer";
import { ProductCard } from "@/components/product/ProductCard";
import { ProductGridSkeleton } from "@/components/listing/ProductGridSkeleton";
import { SORT_OPTIONS } from "@/lib/constants";
import { pluralize } from "@/lib/format";
import { serializeQuery } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import type { Listing, ListingQuery, RangeFilterValue, SortOption } from "@/lib/types";

/**
 * Выдача поиска с фильтрами, сортировкой и пагинацией (DRF-1166).
 *
 * Отдельный компонент, а не `ListingShell`: тот на 600 строк и построен вокруг
 * категории — хлебные крошки раздела, `CategoryHero`, JSON-LD, панель типов
 * инструмента. Поиску всё это чуждо, а «категория-призрак» ради переиспользования
 * протащила бы на страницу лишнюю разметку. Кирпичи при этом общие: сайдбар,
 * мобильный drawer, карточка товара, скелет.
 *
 * Фасета три — цена, бренд, наличие (см. `build_search_facets`): выдача поиска
 * смешанная, технические характеристики в ней описывали бы меньшинство товаров.
 */
export function SearchShell({
  listing,
  query,
  q,
}: {
  listing: Listing;
  query: ListingQuery;
  q: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [isPending, startTransition] = useTransition();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const totalPages = Math.max(1, Math.ceil(listing.total / query.perPage));
  const page = Math.min(Math.max(1, query.page), totalPages);

  // Запрос живёт в URL отдельно от состояния листинга: serializeQuery про него не знает.
  const push = (next: ListingQuery) => {
    const qs = serializeQuery(next);
    const params = new URLSearchParams(qs);
    params.set("q", q);
    startTransition(() => {
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    });
  };

  const setSort = (sort: SortOption) => push({ ...query, sort, page: 1 });
  const setPage = (p: number) => push({ ...query, page: p });

  const toggleCheckbox = (code: string, value: string) => {
    const cur = Array.isArray(query.filters[code]) ? (query.filters[code] as string[]) : [];
    const nextVals = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
    const filters = { ...query.filters };
    if (nextVals.length) filters[code] = nextVals;
    else delete filters[code];
    push({ ...query, filters, page: 1 });
  };

  const setRange = (code: string, val: { min?: number; max?: number }) => {
    const filters = { ...query.filters };
    if (val.min == null && val.max == null) delete filters[code];
    else filters[code] = val as RangeFilterValue;
    push({ ...query, filters, page: 1 });
  };

  const resetAll = () => push({ ...query, filters: {}, page: 1 });

  const activeFiltersCount = Object.keys(query.filters).length;

  // Оконная пагинация (1 … p-1 p p+1 … N) — как в каталоге.
  const pageItems: (number | "…")[] = [];
  {
    const set = new Set<number>([1, totalPages, page, page - 1, page + 1]);
    const nums = [...set].filter((n) => n >= 1 && n <= totalPages).sort((a, b) => a - b);
    let prev = 0;
    for (const n of nums) {
      if (n - prev > 1) pageItems.push("…");
      pageItems.push(n);
      prev = n;
    }
  }

  const chips = Object.entries(query.filters).map(([code, val]) => ({
    key: code,
    label: Array.isArray(val) ? `${code}: ${val.join(", ")}` : code,
    onRemove: () => {
      const filters = { ...query.filters };
      delete filters[code];
      push({ ...query, filters, page: 1 });
    },
  }));

  const sidebar = (
    <FacetSidebar
      facets={listing.facets}
      filters={query.filters}
      onToggle={toggleCheckbox}
      onRange={setRange}
      total={listing.total}
      resultsHref="#products"
    />
  );

  return (
    <div className="mt-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-3">
          Найдено {listing.total} {pluralize(listing.total, "товар", "товара", "товаров")}
        </p>
        <div className="flex items-center gap-2">
          <button
            ref={filterBtnRef}
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-line px-3 text-sm text-ink-2 lg:hidden"
          >
            <SlidersHorizontal className="h-4 w-4" aria-hidden />
            Фильтры{activeFiltersCount ? ` ${activeFiltersCount}` : ""}
          </button>
          <label className="flex items-center gap-2 text-sm text-ink-3">
            <span className="hidden sm:inline">Сортировка</span>
            <select
              value={query.sort}
              onChange={(e) => setSort(e.target.value as SortOption)}
              aria-label="Сортировка"
              className="h-9 rounded-md border border-line bg-surface px-2 text-sm text-ink"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {/* Без явной сортировки поиск ранжирует по релевантности — так и подписано. */}
                  {o.value === "popular" ? "Сначала подходящие" : o.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="hidden lg:block">{sidebar}</aside>

        <div id="products" aria-busy={isPending} className="scroll-mt-24">
          {isPending ? (
            <ProductGridSkeleton view="grid" count={Math.min(query.perPage, 12)} />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {listing.products.map((p) => (
                <ProductCard key={p.id} product={p} view="grid" />
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <nav
              aria-label="Пагинация"
              className="mt-6 flex flex-wrap items-center justify-center gap-1"
            >
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 disabled:opacity-40"
              >
                ‹
              </button>
              {pageItems.map((it, i) =>
                it === "…" ? (
                  <span key={`gap-${i}`} className="px-2 text-ink-3">
                    …
                  </span>
                ) : (
                  <button
                    key={it}
                    type="button"
                    onClick={() => setPage(it)}
                    aria-current={it === page ? "page" : undefined}
                    className={cn(
                      "min-w-9 rounded-md border px-3 py-1.5 text-sm",
                      it === page ? "border-accent text-accent" : "border-line text-ink-2",
                    )}
                  >
                    {it}
                  </button>
                ),
              )}
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
                className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 disabled:opacity-40"
              >
                ›
              </button>
            </nav>
          )}
        </div>
      </div>

      <MobileFilterDrawer
        open={drawerOpen}
        onClose={closeDrawer}
        total={listing.total}
        onReset={resetAll}
        triggerRef={filterBtnRef}
        chips={chips}
      >
        {sidebar}
      </MobileFilterDrawer>
    </div>
  );
}
