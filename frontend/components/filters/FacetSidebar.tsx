"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import type { Facet, ListingQuery, RangeFilterValue } from "@/lib/types";
import { groupSidebarFacets, pricePresets } from "@/lib/listing";
import { pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

// Шаг слайдера диапазона: для цены крупнее, прочее — 1.
const RANGE_STEP: Record<string, number> = { price: 100 };

type Props = {
  facets: Facet[];
  filters: ListingQuery["filters"];
  onToggle: (code: string, value: string) => void;
  onRange: (code: string, val: { min?: number; max?: number }) => void;
  /** Встроить в общую карточку с навигацией раздела. */
  connected?: boolean;
  /** Сколько товаров в текущей выдаче — для кнопки «Показать N товаров» (макет Cat2). */
  total?: number;
  /** Якорь сетки товаров. Кнопка не применяет фильтры (они применяются сразу),
      а прокручивает к результату — на десктопе сайдбар длиннее первого экрана. */
  resultsHref?: string;
};

// Сворачиваемый блок фасета с заголовком и шевроном (по макету Cat2). Свёрнут по
// умолчанию: открытыми все секции занимали два экрана, и до товаров нужно было
// прокручивать мимо фильтров, которыми человек не пользовался. Открытым остаётся
// только блок цены — им пользуются чаще всего.
function FacetBlock({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details open={defaultOpen} className="group border-t border-line py-4 first:border-t-0 first:pt-0">
      <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold text-ink">
        {title}
        <ChevronDown className="h-4 w-4 text-ink-3 transition group-open:rotate-180" aria-hidden />
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

export function FacetSidebar({
  facets,
  filters,
  onToggle,
  onRange,
  connected = false,
  total,
  resultsHref,
}: Props) {
  // tool_type (isNav) — навигация, рендерится капсулами в шапке раздела (CategoryNavStrip),
  // а НЕ фасетом сайдбара (§3.1, §23.5).
  const visibleFacets = facets.filter((f) => !f.isNav);
  const sections = groupSidebarFacets(visibleFacets);

  const renderFacet = (f: Facet, open = true) => {
    const unit = f.type !== "checkbox" && f.unit ? `, ${f.unit}` : "";
    return f.type === "checkbox" ? (
      <FacetBlock key={f.code} title={f.label} defaultOpen={open}>
        <CheckboxFacet facet={f} onToggle={onToggle} />
      </FacetBlock>
    ) : (
      <FacetBlock key={f.code} title={`${f.label}${unit}`} defaultOpen={open}>
        <RangeFacet
          key={`${f.code}-${f.min ?? ""}-${f.max ?? ""}-${(filters[f.code] as RangeFilterValue | undefined)?.min ?? ""}-${(filters[f.code] as RangeFilterValue | undefined)?.max ?? ""}`}
          facet={f}
          value={(filters[f.code] as RangeFilterValue) ?? {}}
          onRange={onRange}
        />
      </FacetBlock>
    );
  };

  // «Фильтры/Сбросить все» вынесены в тулбар над выдачей — в сайдбаре только сами фасеты.
  // Секция «extra» (§7.2) — свёрнута по умолчанию.
  return (
    <div
      className={
        connected
          ? "rounded-none border-0 bg-transparent px-5 py-4"
          : "rounded-lg border border-line bg-surface p-4"
      }
    >
      {sections.map((section) => section.facets.map((f) => renderFacet(f, f.code === "price")))}

      {/* «Показать N товаров» — не «применить»: фильтры применяются сразу, кнопка
          прокручивает к выдаче. В мобильном drawer своя такая кнопка (она ещё и
          закрывает drawer), поэтому здесь только для десктопной колонки. */}
      {resultsHref && total != null && (
        <a
          href={resultsHref}
          className="mt-4 flex min-h-11 w-full items-center justify-center rounded-md border border-accent bg-surface text-sm font-semibold text-accent transition hover:bg-accent/5"
        >
          Показать {total} {pluralize(total, "товар", "товара", "товаров")}
        </a>
      )}
    </div>
  );
}

function CheckboxFacet({
  facet,
  onToggle,
}: {
  facet: Facet;
  onToggle: (code: string, value: string) => void;
}) {
  const [q, setQ] = useState("");
  const [expanded, setExpanded] = useState(false);
  const searchable = facet.code === "brand";
  const opts = (facet.options ?? []).filter((o) =>
    o.label.toLowerCase().includes(q.toLowerCase()),
  );
  const visible = expanded ? opts : opts.slice(0, 6);

  return (
    <fieldset className="border-0 p-0" aria-label={facet.label}>
      {searchable && (
        <div className="relative mb-2">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Поиск бренда"
            className="h-9 w-full rounded-md border border-line bg-surface pl-9 pr-3 text-sm text-ink placeholder:text-ink-3"
          />
        </div>
      )}

      <div className="flex flex-col">
        {visible.map((o) => (
          <label
            key={o.value}
            className="flex min-h-11 cursor-pointer items-center gap-2.5 text-sm text-ink-2 hover:text-ink md:min-h-9"
          >
            <input
              type="checkbox"
              checked={o.selected}
              onChange={() => onToggle(facet.code, o.value)}
              className="peer sr-only"
            />
            {/* Кастомный зелёный чекбокс (по макету). */}
            <span
              aria-hidden
              className="grid h-5 w-5 shrink-0 place-items-center rounded border border-line text-transparent transition peer-checked:border-accent peer-checked:bg-accent peer-checked:text-accent-ink peer-focus-visible:ring-2 peer-focus-visible:ring-accent"
            >
              <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none" aria-hidden>
                <path
                  d="M2 6.5 4.5 9 10 3"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <span className="flex-1">{o.label}</span>
            <span className="text-xs text-ink-3">{o.count}</span>
          </label>
        ))}
      </div>

      {opts.length > 6 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-sm font-medium text-accent hover:underline"
        >
          {expanded ? "Свернуть" : `Показать ещё (${opts.length - 6})`}
        </button>
      )}
    </fieldset>
  );
}

function RangeFacet({
  facet,
  value,
  onRange,
}: {
  facet: Facet;
  value: RangeFilterValue;
  onRange: (code: string, val: { min?: number; max?: number }) => void;
}) {
  const lo = facet.min;
  const hi = facet.max;
  const disabled = lo == null || hi == null || lo >= hi;

  // Границы из URL могут не попадать в шкалу новой выдачи: сменили тип инструмента —
  // цены другие, а price_max остался прежним. Показываем зажатыми в шкалу, иначе
  // бегунок улетает за край, а число в поле спорит с подписями пресетов. Сам фильтр
  // в URL чистит ListingShell (normalizeRangeFilters).
  const clamp = (v: number) => Math.min(Math.max(v, lo ?? v), hi ?? v);
  const [draft, setDraft] = useState({
    min: clamp(value.min ?? lo ?? 0),
    max: clamp(value.max ?? hi ?? 0),
  });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  function clearTimer() {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }

  if (disabled) {
    return <p className="text-xs text-ink-3">Диапазон недоступен</p>;
  }

  const step = RANGE_STEP[facet.code] ?? 1;

  const commit = (d: { min: number; max: number }) => {
    onRange(facet.code, {
      min: d.min <= lo ? undefined : d.min,
      max: d.max >= hi ? undefined : d.max,
    });
  };
  const debounced = (d: { min: number; max: number }) => {
    clearTimer();
    timer.current = setTimeout(() => commit(d), 300);
  };
  const flush = (d: { min: number; max: number }) => {
    clearTimer();
    commit(d);
  };

  const setMin = (raw: number, immediate: boolean) => {
    const min = Math.min(Math.max(Number.isFinite(raw) ? raw : lo, lo), draft.max);
    const next = { min, max: draft.max };
    setDraft(next);
    (immediate ? flush : debounced)(next);
  };
  const setMax = (raw: number, immediate: boolean) => {
    const max = Math.max(Math.min(Number.isFinite(raw) ? raw : hi, hi), draft.min);
    const next = { min: draft.min, max };
    setDraft(next);
    (immediate ? flush : debounced)(next);
  };
  const fieldNum = (s: string, fallback: number) => (s === "" ? fallback : Number(s));
  const fieldCls =
    "h-9 w-full rounded-md border border-line bg-surface px-2 text-sm text-ink placeholder:text-ink-3";

  const span = hi - lo || 1;
  const minPct = ((draft.min - lo) / span) * 100;
  const maxPct = ((draft.max - lo) / span) * 100;

  // Пресеты цены (макет Cat2). Пороги и отбор — в lib/listing.pricePresets: оттуда же
  // их видят тесты, и оттуда же отсеиваются варианты, дающие ноль товаров или ничего
  // не сужающие (такие normalizeRangeFilters всё равно сбросит, и нажатие выглядело бы
  // как «ничего не произошло»).
  const presets = facet.code === "price" ? pricePresets(lo, hi) : [];

  const applyPreset = (min?: number, max?: number) => {
    const d = { min: Math.max(min ?? lo, lo), max: Math.min(max ?? hi, hi) };
    setDraft(d);
    flush(d);
  };

  return (
    <fieldset className="border-0 p-0" aria-label={facet.label}>
      <div className="mb-3 flex items-center gap-2">
        <input
          type="number"
          inputMode="numeric"
          value={draft.min}
          min={lo}
          max={hi}
          step={step}
          aria-label={`${facet.label} — от`}
          onChange={(e) => setDraft({ min: fieldNum(e.target.value, lo), max: draft.max })}
          onBlur={(e) => setMin(fieldNum(e.target.value, lo), true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") setMin(fieldNum((e.target as HTMLInputElement).value, lo), true);
          }}
          className={fieldCls}
        />
        <span className="text-ink-3">—</span>
        <input
          type="number"
          inputMode="numeric"
          value={draft.max}
          min={lo}
          max={hi}
          step={step}
          aria-label={`${facet.label} — до`}
          onChange={(e) => setDraft({ min: draft.min, max: fieldNum(e.target.value, hi) })}
          onBlur={(e) => setMax(fieldNum(e.target.value, hi), true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") setMax(fieldNum((e.target as HTMLInputElement).value, hi), true);
          }}
          className={fieldCls}
        />
      </div>

      <div className="range-dual mb-3">
        <div className="range-track" />
        <div className="range-fill" style={{ left: `${minPct}%`, right: `${100 - maxPct}%` }} />
        <input
          type="range"
          min={lo}
          max={hi}
          step={step}
          value={draft.min}
          aria-label={`${facet.label} — минимум`}
          onChange={(e) => setMin(Number(e.target.value), false)}
          onPointerUp={(e) => setMin(Number((e.target as HTMLInputElement).value), true)}
          onKeyUp={(e) => setMin(Number((e.target as HTMLInputElement).value), true)}
          style={{ zIndex: draft.min >= draft.max ? 5 : 3 }}
        />
        <input
          type="range"
          min={lo}
          max={hi}
          step={step}
          value={draft.max}
          aria-label={`${facet.label} — максимум`}
          onChange={(e) => setMax(Number(e.target.value), false)}
          onPointerUp={(e) => setMax(Number((e.target as HTMLInputElement).value), true)}
          onKeyUp={(e) => setMax(Number((e.target as HTMLInputElement).value), true)}
          style={{ zIndex: 4 }}
        />
      </div>

      {presets.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
          {presets.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => applyPreset(p.min, p.max)}
              className="text-ink-3 hover:text-accent"
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
    </fieldset>
  );
}
