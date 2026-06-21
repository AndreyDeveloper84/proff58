"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { LayoutGrid, List, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Listing, ListingQuery, RangeFilterValue, SortOption } from "@/lib/types";
import { applyListing } from "@/lib/filtering";
import { parseQuery, serializeQuery } from "@/lib/url-state";
import { PER_PAGE_OPTIONS, SORT_OPTIONS } from "@/lib/constants";
import { ProductCard } from "@/components/product/ProductCard";
import { FacetSidebar } from "@/components/filters/FacetSidebar";

export function ListingShell({
  listing,
  categorySlug,
}: {
  listing: Listing;
  categorySlug: string;
}) {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const query = useMemo(
    () => parseQuery(new URLSearchParams(sp.toString()), categorySlug),
    [sp, categorySlug],
  );
  const result = useMemo(() => applyListing(listing, query), [listing, query]);

  const push = useCallback(
    (next: ListingQuery) => {
      const qs = serializeQuery(next);
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname],
  );

  const setView = (view: "grid" | "list") => push({ ...query, view });
  const setSort = (sort: SortOption) => push({ ...query, sort, page: 1 });
  const setPerPage = (perPage: number) => push({ ...query, perPage, page: 1 });
  const setPage = (page: number) => push({ ...query, page });

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

  // Чипы применённых фильтров
  const chips: { code: string; value?: string; label: string }[] = [];
  for (const [code, val] of Object.entries(query.filters)) {
    const facet = listing.facets.find((f) => f.code === code);
    if (Array.isArray(val)) {
      for (const v of val) {
        const opt = facet?.options?.find((o) => o.value === v);
        chips.push({ code, value: v, label: opt?.label ?? v });
      }
    } else {
      const unit = facet?.unit ? ` ${facet.unit}` : "";
      const parts: string[] = [];
      if (val.min != null) parts.push(`от ${val.min}`);
      if (val.max != null) parts.push(`до ${val.max}`);
      chips.push({ code, label: `${facet?.label ?? code}: ${parts.join(" ")}${unit}` });
    }
  }
  const removeChip = (code: string, value?: string) =>
    value ? toggleCheckbox(code, value) : setRange(code, {});

  const sidebar = (
    <FacetSidebar
      facets={result.facets}
      filters={query.filters}
      onToggle={toggleCheckbox}
      onRange={setRange}
      onReset={resetAll}
    />
  );

  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6">
      <nav aria-label="Хлебные крошки" className="mb-3 flex flex-wrap items-center gap-1 text-xs text-ink-3">
        {listing.category.breadcrumb.map((b, i) => (
          <span key={b.href} className="flex items-center gap-1">
            {i > 0 && <span className="text-ink-3">/</span>}
            <a href={b.href} className="hover:text-accent">
              {b.label}
            </a>
          </span>
        ))}
      </nav>

      <div className="mb-5 grid gap-4 lg:grid-cols-[1fr_320px]">
        <div>
          <h1 className="font-display text-3xl font-semibold uppercase tracking-wide text-ink">
            {listing.category.title}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-ink-2">{listing.category.intro}</p>
        </div>
        {listing.promo && (
          <a
            href={listing.promo.href}
            className="flex flex-col justify-center rounded-lg border border-line bg-raised p-4 transition hover:border-accent"
          >
            <span className="text-xs text-ink-3">{listing.promo.title}</span>
            <span className="mt-1 font-display text-lg font-semibold text-accent">
              {listing.promo.subtitle}
            </span>
          </a>
        )}
      </div>

      {listing.subcategories.length > 0 && (
        <div className="mb-5 flex flex-wrap gap-2">
          {listing.subcategories.map((s) => (
            <a
              key={s.label}
              href={s.href}
              className="rounded-full border border-line bg-surface px-3 py-1 text-sm text-ink-2 transition hover:border-accent hover:text-accent"
            >
              {s.label}
            </a>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <aside className="hidden lg:block">{sidebar}</aside>

        <div className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2">
            <span className="text-sm text-ink-2">Найдено {result.total}</span>
            <div className="flex flex-wrap items-center gap-3">
              <details className="lg:hidden">
                <summary className="cursor-pointer rounded-md border border-line px-3 py-1.5 text-sm text-ink-2">
                  Фильтры
                </summary>
                <div className="mt-3">{sidebar}</div>
              </details>

              <label className="flex items-center gap-2 text-sm text-ink-3">
                Сортировка
                <select
                  value={query.sort}
                  onChange={(e) => setSort(e.target.value as SortOption)}
                  className="rounded-md border border-line bg-canvas px-2 py-1 text-sm text-ink"
                >
                  {SORT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-2 text-sm text-ink-3">
                По
                <select
                  value={query.perPage}
                  onChange={(e) => setPerPage(Number(e.target.value))}
                  className="rounded-md border border-line bg-canvas px-2 py-1 text-sm text-ink"
                >
                  {PER_PAGE_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>

              <div className="flex items-center gap-1" role="group" aria-label="Вид списка">
                <button
                  type="button"
                  aria-label="Сеткой"
                  aria-pressed={query.view === "grid"}
                  onClick={() => setView("grid")}
                  className={cn(
                    "grid h-8 w-8 place-items-center rounded-md border border-line",
                    query.view === "grid" ? "border-accent text-accent" : "text-ink-3",
                  )}
                >
                  <LayoutGrid className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label="Списком"
                  aria-pressed={query.view === "list"}
                  onClick={() => setView("list")}
                  className={cn(
                    "grid h-8 w-8 place-items-center rounded-md border border-line",
                    query.view === "list" ? "border-accent text-accent" : "text-ink-3",
                  )}
                >
                  <List className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          {chips.length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {chips.map((c) => (
                <button
                  key={`${c.code}-${c.value ?? "range"}`}
                  type="button"
                  onClick={() => removeChip(c.code, c.value)}
                  className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-ink-2 hover:border-accent"
                >
                  {c.label}
                  <X className="h-3 w-3" />
                </button>
              ))}
              <button
                type="button"
                onClick={resetAll}
                className="text-xs text-ink-3 underline hover:text-accent"
              >
                Сбросить всё
              </button>
            </div>
          )}

          {result.products.length === 0 ? (
            <div className="rounded-lg border border-line bg-surface p-10 text-center">
              <p className="text-ink-2">
                По этим фильтрам товаров нет. Сбросьте цену или бренд.
              </p>
              <button
                type="button"
                onClick={resetAll}
                className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
              >
                Сбросить фильтры
              </button>
            </div>
          ) : query.view === "list" ? (
            <div className="flex flex-col gap-3">
              {result.products.map((p) => (
                <ProductCard key={p.id} product={p} view="list" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
              {result.products.map((p) => (
                <ProductCard key={p.id} product={p} view="grid" />
              ))}
            </div>
          )}

          {result.totalPages > 1 && (
            <nav
              aria-label="Пагинация"
              className="mt-6 flex items-center justify-center gap-1"
            >
              <button
                type="button"
                disabled={result.page <= 1}
                onClick={() => setPage(result.page - 1)}
                className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 disabled:opacity-40"
              >
                ‹
              </button>
              {Array.from({ length: result.totalPages }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setPage(n)}
                  aria-current={n === result.page ? "page" : undefined}
                  className={cn(
                    "min-w-9 rounded-md border px-3 py-1.5 text-sm",
                    n === result.page ? "border-accent text-accent" : "border-line text-ink-2",
                  )}
                >
                  {n}
                </button>
              ))}
              <button
                type="button"
                disabled={result.page >= result.totalPages}
                onClick={() => setPage(result.page + 1)}
                className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 disabled:opacity-40"
              >
                ›
              </button>
            </nav>
          )}
        </div>
      </div>
    </div>
  );
}
