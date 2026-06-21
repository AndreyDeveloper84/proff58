"use client";

import { useState } from "react";
import type { Facet, ListingQuery, RangeFilterValue } from "@/lib/types";

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
            key={`${f.code}-${(filters[f.code] as RangeFilterValue | undefined)?.min ?? ""}-${(filters[f.code] as RangeFilterValue | undefined)?.max ?? ""}`}
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
  const toNum = (s: string) => (s === "" ? undefined : Number(s));
  return (
    <fieldset className="border-0 p-0" aria-label={facet.label}>
      <legend className="mb-2 text-sm font-medium text-ink">{facet.label}</legend>
      <div className="flex items-center gap-2">
        <input
          type="number"
          inputMode="numeric"
          defaultValue={value.min ?? ""}
          placeholder={facet.min != null ? `от ${facet.min}` : "от"}
          aria-label={`${facet.label} — от`}
          onBlur={(e) => onRange(facet.code, { min: toNum(e.target.value), max: value.max })}
          className="w-full rounded-md border border-line bg-canvas px-2 py-1 text-sm text-ink placeholder:text-ink-3"
        />
        <span className="text-ink-3">—</span>
        <input
          type="number"
          inputMode="numeric"
          defaultValue={value.max ?? ""}
          placeholder={facet.max != null ? `до ${facet.max}` : "до"}
          aria-label={`${facet.label} — до`}
          onBlur={(e) => onRange(facet.code, { min: value.min, max: toNum(e.target.value) })}
          className="w-full rounded-md border border-line bg-canvas px-2 py-1 text-sm text-ink placeholder:text-ink-3"
        />
      </div>
    </fieldset>
  );
}
