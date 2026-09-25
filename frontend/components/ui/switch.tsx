"use client";

import { cn } from "@/lib/utils";

// Доступный toggle (#519): нативный checkbox role="switch" + sr-only, чтобы
// клавиатура/screen reader работали из коробки (Space/Enter, aria-checked
// озвучивается автоматически по role=switch+checked) — трек/thumb только
// визуальные, aria-hidden.
export function Switch({
  checked,
  onChange,
  disabled,
  label,
  id,
  className,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  /**
   * Имя для screen reader (sr-only). Опционален только если у инпута уже
   * есть внешний `<label htmlFor={id}>` — иначе обязателен: это единственный
   * источник accessible name (умышленно НЕ дублируем внешним `label htmlFor`
   * на том же id — двойная связка label путает часть screen reader'ов).
   */
  label?: string;
  id?: string;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors",
        checked ? "bg-accent" : "bg-line",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
    >
      <input
        id={id}
        type="checkbox"
        role="switch"
        aria-checked={checked}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="peer absolute inset-0 h-full w-full cursor-pointer opacity-0"
      />
      {label && <span className="sr-only">{label}</span>}
      <span
        aria-hidden
        className={cn(
          "pointer-events-none inline-block h-5 w-5 translate-x-0.5 rounded-full bg-white shadow transition-transform",
          checked && "translate-x-[22px]",
        )}
      />
      <span className="pointer-events-none absolute inset-0 rounded-full ring-offset-2 peer-focus-visible:ring-2 peer-focus-visible:ring-accent" />
    </label>
  );
}
