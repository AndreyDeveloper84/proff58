"use client";

import { useCallback, useRef, useState, useTransition } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LayoutGrid, List, SlidersHorizontal, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Listing, ListingQuery, RangeFilterValue, SortOption } from "@/lib/types";
import { serializeQuery } from "@/lib/url-state";
import { humanizeToken, rangeChipLabel } from "@/lib/format";
import { categoryNav, sidebarFacets } from "@/lib/listing";
import { track } from "@/lib/analytics";
import { PER_PAGE_OPTIONS, SORT_OPTIONS } from "@/lib/constants";
import { ProductCard } from "@/components/product/ProductCard";
import { FacetSidebar } from "@/components/filters/FacetSidebar";
import { CategoryNavStrip } from "@/components/listing/CategoryNav";
import { ProductGridSkeleton } from "@/components/listing/ProductGridSkeleton";
import { BreadcrumbsJsonLd } from "./BreadcrumbsJsonLd";
import { CategoryHero } from "@/components/listing/CategoryHero";
import { MobileFilterDrawer } from "@/components/listing/MobileFilterDrawer";

// Презентационный shell: данные уже разрешены на сервере (getListing(query)).
// Никакой клиентской фильтрации — изменение фильтра меняет URL (router.replace),
// сервер пересобирает сегмент и отдаёт новый listing. Подходит для тысяч товаров.
export function ListingShell({
  listing,
  query,
}: {
  listing: Listing;
  query: ListingQuery;
}) {
  const router = useRouter();
  const pathname = usePathname();
  // useTransition: навигация (router.replace) внутри startTransition даёт isPending на время
  // серверного раунд-трипа → показываем skeleton карточек вместо full-page spinner (§15).
  const [isPending, startTransition] = useTransition();
  // Мобильный drawer фильтров (§4).
  const [drawerOpen, setDrawerOpen] = useState(false);
  const filterBtnRef = useRef<HTMLButtonElement>(null);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const totalPages = Math.max(1, Math.ceil(listing.total / query.perPage));
  const page = Math.min(Math.max(1, query.page), totalPages);

  const push = (next: ListingQuery) => {
    const qs = serializeQuery(next);
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    });
  };

  const setView = (view: "grid" | "list") => push({ ...query, view });
  const setSort = (sort: SortOption) => push({ ...query, sort, page: 1 });
  const setPerPage = (perPage: number) => push({ ...query, perPage, page: 1 });
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

  // Снять фильтр целиком (чекбокс-код со всеми значениями или диапазон) — для точечного сброса.
  const clearFilter = (code: string) => {
    const filters = { ...query.filters };
    delete filters[code];
    push({ ...query, filters, page: 1 });
  };

  // reset all сбрасывает И тип, И все фильтры (§3.5), но НЕ трогает sort/view/per_page.
  const resetAll = () => push({ ...query, toolType: undefined, filters: {}, page: 1 });

  // --- Навигация раздела: подкатегории-ссылки либо типы инструмента (§3.1) ---
  const navFacet = listing.facets.find((f) => f.isNav);
  const nav = categoryNav(listing, query.category, query.toolType);
  const activeFiltersCount = Object.keys(query.filters).length;
  // Подпись активного типа: из nav-фасета, иначе (тип «вымылся» прочими фильтрами, §14)
  // humanizeToken(slug) — тот же фолбэк, что и в синтетическом пункте categoryNav (N3).
  const activeToolTypeLabel = query.toolType
    ? (navFacet?.options?.find((o) => o.value === query.toolType)?.label ??
      humanizeToken(query.toolType))
    : "";

  // Применить/снять тип. next=null — снятие. Аналитика tool_type_select (§21): result_count —
  // текущая выдача (точное число после навигации известно только следующему рендеру).
  const applyToolType = (next: string | null, label: string) => {
    track({
      name: "tool_type_select",
      payload: {
        category_slug: query.category,
        tool_type_slug: next,
        tool_type_label: next ? label : null,
        result_count: listing.total,
        previous_tool_type: query.toolType ?? null,
        active_filters_count: activeFiltersCount,
      },
    });
    push({ ...query, toolType: next ?? undefined, page: 1 });
  };
  // Клик по плитке: повторный по активному → снять, иначе выбрать (§3.1, §7.1).
  const onSelectType = (slug: string, label: string) =>
    applyToolType(query.toolType === slug ? null : slug, label);

  const sortOptions = listing.sort.length ? listing.sort : SORT_OPTIONS;

  // Чипы применённых фильтров (C-lite). Каждый чип знает свой сброс. Тип — отдельный спокойный
  // чип «Тип: <Имя>» (§9.1), диапазоны — по-русски с единицами «… от 10,5 до 20 мм» (§9.2).
  const chips: { key: string; label: string; onRemove: () => void }[] = [];
  if (query.toolType) {
    chips.push({
      key: "tool_type",
      label: `Тип: ${activeToolTypeLabel}`,
      onRemove: () => applyToolType(null, activeToolTypeLabel),
    });
  }
  for (const [code, val] of Object.entries(query.filters)) {
    const facet = listing.facets.find((f) => f.code === code);
    if (Array.isArray(val)) {
      for (const v of val) {
        const opt = facet?.options?.find((o) => o.value === v);
        chips.push({
          key: `${code}:${v}`,
          label: opt?.label ?? v,
          onRemove: () => toggleCheckbox(code, v),
        });
      }
    } else {
      chips.push({
        key: code,
        label: rangeChipLabel(facet?.label ?? code, val.min, val.max, facet?.unit),
        onRemove: () => setRange(code, {}),
      });
    }
  }

  // Точечный сброс для empty-state (§12.3, §14): по одному предложению на активное ограничение.
  const resetSuggestions: { key: string; label: string; onClick: () => void }[] = [];
  if (query.toolType) {
    resetSuggestions.push({
      key: "tool_type",
      label: `Снять тип: ${activeToolTypeLabel}`,
      onClick: () => applyToolType(null, activeToolTypeLabel),
    });
  }
  for (const [code, val] of Object.entries(query.filters)) {
    const facet = listing.facets.find((f) => f.code === code);
    const name = facet?.label ?? code;
    resetSuggestions.push({
      key: code,
      label: Array.isArray(val) ? `Снять «${name}»` : `Сбросить «${name}»`,
      onClick: () => clearFilter(code),
    });
  }
  // §12.3/§14: числовой EAV-диапазон скрывает товары без характеристики — поясняем причину.
  const hasAttrRange = Object.entries(query.filters).some(
    ([code, val]) => !Array.isArray(val) && code.startsWith("attr_"),
  );

  // Оконная пагинация (1 … p-1 p p+1 … N) — не рендерим сотни кнопок.
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

  // Контекстный гейтинг (§6): на широкой категории без выбранного типа — только базовые
  // фильтры; после выбора tool_type / на листовой — все пришедшие. Применённые chips и
  // восстановление из URL не затронуты (работают по query.filters, а не по составу сайдбара).
  const visibleFacets = sidebarFacets(listing, query.toolType);
  const sidebar = (
    <FacetSidebar
      facets={visibleFacets}
      filters={query.filters}
      onToggle={toggleCheckbox}
      onRange={setRange}
    />
  );

  return (
    <div className="mx-auto w-full max-w-[1680px] px-4 py-6 sm:px-6 xl:px-8">
      <BreadcrumbsJsonLd crumbs={listing.category.breadcrumb} />
      <nav aria-label="Хлебные крошки" className="mb-3 flex flex-wrap items-center gap-1 text-xs text-ink-3">
        {listing.category.breadcrumb.map((b, i, all) => {
          // Последняя крошка — это сама открытая страница: ссылка на себя ведёт
          // в никуда и сбивает («нажал — ничего не произошло»).
          const current = i === all.length - 1;
          return (
            <span key={`${b.href}-${i}`} className="flex items-center gap-1">
              {i > 0 && <span className="text-ink-3">/</span>}
              {current ? (
                <span aria-current="page" className="text-ink-2">
                  {b.label}
                </span>
              ) : (
                <a href={b.href} className="hover:text-accent">
                  {b.label}
                </a>
              )}
            </span>
          );
        })}
      </nav>

      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        <aside className="hidden lg:block">
          {/* Единый «пульт подбора»: шапка, активные условия, навигация и фасеты
              начинаются сразу под хлебными крошками. Панель следует за пользователем
              от нижнего края шапки до конца всей каталожной колонки. */}
          <div className="sticky top-[104px] max-h-[calc(100vh-120px)] divide-y divide-line overflow-x-hidden overflow-y-auto rounded-xl border border-line border-t-2 border-t-accent bg-raised/60 shadow-sm">
            <div className="bg-surface/80 px-5 py-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent">
                    <SlidersHorizontal className="h-4 w-4" aria-hidden />
                  </span>
                  <div className="flex min-w-0 items-center gap-2">
                    <h2 className="font-display text-lg font-semibold text-ink">Фильтры</h2>
                    {chips.length > 0 && (
                      <span className="grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1.5 text-[11px] font-bold text-accent-ink">
                        {chips.length}
                      </span>
                    )}
                  </div>
                </div>

                {chips.length > 0 && (
                  <button
                    type="button"
                    onClick={resetAll}
                    className="shrink-0 text-xs font-medium text-accent hover:underline"
                  >
                    Сбросить
                  </button>
                )}
              </div>

              <p className="mt-2 text-xs leading-relaxed text-ink-3">
                Подберите инструмент по нужным параметрам
              </p>

              {chips.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Активные фильтры">
                  {chips.map((chip) => (
                    <button
                      key={chip.key}
                      type="button"
                      onClick={chip.onRemove}
                      title={`Убрать: ${chip.label}`}
                      className="inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-md border border-accent/30 bg-accent/5 px-2 py-1 text-xs text-accent transition hover:border-accent"
                    >
                      <span className="truncate">{chip.label}</span>
                      <X className="h-3 w-3 shrink-0" aria-hidden />
                    </button>
                  ))}
                </div>
              )}
            </div>
            <FacetSidebar
              facets={visibleFacets}
              filters={query.filters}
              onToggle={toggleCheckbox}
              onRange={setRange}
              connected
            />
          </div>
        </aside>

        <div className="min-w-0">
          <CategoryHero
            title={listing.category.title}
            intro={listing.category.intro}
            hero={listing.category.hero}
            total={listing.total}
            variant="inline"
            className="mb-4 w-full min-w-0"
            // Хлебные крошки идут от корня, поэтому ближайший родитель — предпоследний;
            // «Главная» и «Каталог» в подборе чертежа просто ни с чем не совпадут.
            parentTitles={listing.category.breadcrumb
              .slice(0, -1)
              .map((crumb) => crumb.label)
              .reverse()}
          />

          {/* Капсулы разделов и типов — сразу под шапкой раздела, а не в
              фильтрах: подкатегория это переход на другую страницу, и прятать
              её за кнопкой «Фильтры» значит сделать вид, что её нет.
              Отдельным блоком, а не внутри шапки: там ряд попадал под
              overflow-hidden и узкую колонку с чертежом — часть капсул просто
              обрезалась, и человек их не видел. */}
          {nav && <CategoryNavStrip nav={nav} onSelect={onSelectType} />}

          {listing.promo && (
            <a
              href={listing.promo.href}
              className="mb-4 flex flex-col justify-center rounded-lg border border-line bg-raised p-4 transition hover:border-accent lg:max-w-md"
            >
              <span className="text-xs text-ink-3">{listing.promo.title}</span>
              <span className="mt-1 font-display text-lg font-semibold text-accent">
                {listing.promo.subtitle}
              </span>
            </a>
          )}

          {/* Панель фильтров (§9.1): триггер сайдбара + сброс + активные чипы (зелёные). */}
          <div className="mb-4 flex flex-wrap items-center gap-3 lg:hidden">
            {/* Мобильный триггер drawer'а фильтров (§4) */}
            <button
              ref={filterBtnRef}
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-haspopup="dialog"
              aria-expanded={drawerOpen}
              className="inline-flex h-11 items-center gap-2 rounded-md border border-line bg-surface px-4 text-sm font-semibold text-ink lg:hidden"
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden />
              Фильтры
              {chips.length > 0 && (
                <span className="grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-[11px] font-bold text-accent-ink">
                  {chips.length}
                </span>
              )}
            </button>
            {chips.length > 0 && (
              <button
                type="button"
                onClick={resetAll}
                className="inline-flex items-center gap-2 text-sm font-medium text-accent hover:underline"
              >
                Сбросить все
              </button>
            )}
            {chips.map((c) => (
              <button
                key={c.key}
                type="button"
                onClick={c.onRemove}
                className="inline-flex items-center gap-2 rounded-md border border-accent/40 bg-accent/5 px-3 py-1.5 text-sm text-accent hover:border-accent"
              >
                {c.label}
                <X className="h-3.5 w-3.5" />
              </button>
            ))}
          </div>

          {/* Строка результатов: сортировка + счётчик показанных + вид списка.
              На телефоне это grid из двух строк («сортировка + вид», под ними
              счётчик и размер страницы) — раскладка в три ряда съедала пол-экрана
              до первого товара. С sm раскладка снова flex: сортировка слева,
              остальное прижато вправо через ml-auto. */}
          <div className="mb-4 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 sm:flex sm:flex-wrap sm:gap-3 lg:rounded-lg lg:border lg:border-line lg:bg-surface lg:px-3 lg:py-1.5">
            <select
              value={query.sort}
              onChange={(e) => setSort(e.target.value as SortOption)}
              aria-label="Сортировка"
              className="row-start-1 h-11 w-full min-w-0 rounded-md border border-line bg-surface px-3 text-sm text-ink sm:w-auto lg:h-8"
            >
              {sortOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>

            <div className="col-span-2 row-start-2 flex items-center justify-between gap-2 sm:ml-auto sm:justify-start sm:gap-3">
              <span
                aria-live="polite"
                className={cn(
                  "text-sm transition-opacity",
                  isPending ? "text-ink-3 opacity-60" : "text-ink-3",
                )}
              >
                Показано {listing.products.length} из {listing.total.toLocaleString("ru-RU")}
              </span>
              <label className="flex items-center gap-2 text-sm text-ink-3">
                На странице
                <select
                  value={query.perPage}
                  onChange={(e) => setPerPage(Number(e.target.value))}
                  className="h-9 rounded-md border border-line bg-surface px-2 text-sm text-ink lg:h-8"
                >
                  {PER_PAGE_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div
              className="col-start-2 row-start-1 flex items-center overflow-hidden rounded-md border border-line"
              role="group"
              aria-label="Вид списка"
            >
              <button
                type="button"
                aria-label="Сеткой"
                aria-pressed={query.view === "grid"}
                onClick={() => setView("grid")}
                className={cn(
                  "grid h-9 w-9 place-items-center lg:h-8 lg:w-8",
                  query.view === "grid" ? "bg-accent text-accent-ink" : "text-ink-3",
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
                  "grid h-9 w-9 place-items-center lg:h-8 lg:w-8",
                  query.view === "list" ? "bg-accent text-accent-ink" : "text-ink-3",
                )}
              >
                <List className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div aria-busy={isPending}>
          {isPending ? (
            // §15: skeleton карточек на время навигации, без full-page spinner.
            <ProductGridSkeleton view={query.view} count={Math.min(query.perPage, 12)} />
          ) : listing.products.length === 0 ? (
            <div className="rounded-lg border border-line bg-surface p-8 text-center">
              <p className="text-ink-2">По выбранным условиям товаров нет.</p>
              {hasAttrRange && (
                // §12.3/§14: числовой фильтр исключает товары без характеристики — объясняем.
                <p className="mt-2 text-sm text-ink-3">
                  Числовой фильтр скрывает товары без этой характеристики — попробуйте расширить
                  диапазон или снять его.
                </p>
              )}
              {resetSuggestions.length > 0 && (
                <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                  {resetSuggestions.map((s) => (
                    <button
                      key={s.key}
                      type="button"
                      onClick={s.onClick}
                      className="rounded-md border border-line bg-canvas px-3 py-1.5 text-sm text-ink-2 hover:border-accent hover:text-accent"
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
              <button
                type="button"
                onClick={resetAll}
                className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
              >
                Сбросить всё
              </button>
            </div>
          ) : query.view === "list" ? (
            <div className="flex flex-col gap-3">
              {listing.products.map((p) => (
                <ProductCard key={p.id} product={p} view="list" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
              {listing.products.map((p) => (
                <ProductCard key={p.id} product={p} view="grid" />
              ))}
            </div>
          )}
          </div>

          {totalPages > 1 && (
            <nav aria-label="Пагинация" className="mt-6 flex flex-wrap items-center justify-center gap-1">
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
