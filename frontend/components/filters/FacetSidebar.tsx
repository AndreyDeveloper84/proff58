"use client";

import { useEffect, useRef, useState } from "react";
import type { Facet, ListingQuery, RangeFilterValue } from "@/lib/types";

// Шаг слайдера диапазона: для цены крупнее, прочее — 1.
const RANGE_STEP: Record<string, number> = { price: 100 };

type Props = {
  facets: Facet[];
  filters: ListingQuery["filters"];
  onToggle: (code: string, value: string) => void;
  onRange: (code: string, val: { min?: number; max?: number }) => void;
  onReset: () => void;
};

export function FacetSidebar({ facets, filters, onToggle, onRange, onReset }: Props) {
  return (
    <div className="flex flex-col gap-5 rounded-lg border border-line bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="font-display text-sm font-semibold uppercase tracking-wide text-ink">
          Фильтры
        </span>
        <button type="button" onClick={onReset} className="text-xs text-ink-3 hover:text-accent">
          Сбросить все
        </button>
      </div>

      {facets.map((f) =>
        f.type === "checkbox" ? (
          <CheckboxFacet key={f.code} facet={f} onToggle={onToggle} />
        ) : (
          <RangeFacet
            key={`${f.code}-${f.min ?? ""}-${f.max ?? ""}-${(filters[f.code] as RangeFilterValue | undefined)?.min ?? ""}-${(filters[f.code] as RangeFilterValue | undefined)?.max ?? ""}`}
            facet={f}
            value={(filters[f.code] as RangeFilterValue) ?? {}}
            onRange={onRange}
          />
        ),
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
      <legend className="mb-2 text-sm font-medium text-ink">{facet.label}</legend>

      {searchable && (
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Поиск бренда"
          className="mb-2 w-full rounded-md border border-line bg-canvas px-2 py-1 text-sm text-ink placeholder:text-ink-3"
        />
      )}

      <div className="flex flex-col gap-1.5">
        {visible.map((o) => (
          <label
            key={o.value}
            className="flex min-h-11 cursor-pointer items-center justify-between gap-2 rounded-md px-1.5 text-sm text-ink-2 hover:bg-raised md:min-h-9"
          >
            <span className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={o.selected}
                onChange={() => onToggle(facet.code, o.value)}
                className="h-4 w-4 accent-[var(--accent)]"
              />
              {o.label}
            </span>
            <span className="text-xs text-ink-3">{o.count}</span>
          </label>
        ))}
      </div>

      {opts.length > 6 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs text-accent"
        >
          {expanded ? "Свернуть" : "Показать ещё"}
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

  // draft — локальное состояние слайдера/полей; коммит в URL отдельно (debounce + flush).
  // Синхронизация с внешним value/bounds — через `key` на компоненте (родитель перемонтирует
  // RangeFacet при сбросе фильтров/смене диапазона), поэтому useState-инициализации достаточно.
  const [draft, setDraft] = useState({ min: value.min ?? lo ?? 0, max: value.max ?? hi ?? 0 });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // cleanup pending debounce при размонтировании (без внешних зависимостей).
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
    return (
      <fieldset className="border-0 p-0" aria-label={facet.label}>
        <legend className="mb-2 text-sm font-medium text-ink">{facet.label}</legend>
        <p className="text-xs text-ink-3">Диапазон недоступен</p>
      </fieldset>
    );
  }

  const step = RANGE_STEP[facet.code] ?? 1;
  const unit = facet.unit ? `, ${facet.unit}` : "";

  // Граница на краю диапазона = «нет ограничения» (undefined) → фильтр снимается.
  const commit = (d: { min: number; max: number }) => {
    onRange(facet.code, { min: d.min <= lo ? undefined : d.min, max: d.max >= hi ? undefined : d.max });
  };
  const debounced = (d: { min: number; max: number }) => {
    clearTimer();
    timer.current = setTimeout(() => commit(d), 300);
  };
  const flush = (d: { min: number; max: number }) => {
    clearTimer();
    commit(d);
  };

  // immediate=false → debounce (drag/стрелки сыплют события); true → сразу (pointerup/blur/Enter).
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
  const rangeCls =
    "pointer-events-none absolute inset-0 h-1 w-full appearance-none bg-transparent " +
    "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-3 " +
    "[&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:appearance-none " +
    "[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent " +
    "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:h-3 " +
    "[&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 " +
    "[&::-moz-range-thumb]:bg-accent";
  const fieldCls =
    "w-full rounded-md border border-line bg-canvas px-2 py-1 text-sm text-ink placeholder:text-ink-3";

  return (
    <fieldset className="border-0 p-0" aria-label={facet.label}>
      <legend className="mb-2 text-sm font-medium text-ink">{`${facet.label}${unit}`}</legend>
      <div className="relative mb-3 h-1 rounded-full bg-line">
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
          className={rangeCls}
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
          className={rangeCls}
        />
      </div>
      <div className="flex items-center gap-2">
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
    </fieldset>
  );
}
