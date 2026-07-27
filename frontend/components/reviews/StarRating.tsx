"use client";

import { Star } from "lucide-react";

// Ввод оценки 1–5 (#573): radiogroup с клавиатурной доступностью.
export function StarRating({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-ink-2">{label}</span>
      <div role="radiogroup" aria-label={label} className="flex gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            aria-label={`Оценка ${n} из 5`}
            onClick={() => onChange(n)}
            className="rounded p-0.5 transition hover:scale-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <Star
              className={n <= value ? "h-6 w-6 fill-amber-400 text-amber-400" : "h-6 w-6 text-ink-3"}
              aria-hidden
            />
          </button>
        ))}
      </div>
    </div>
  );
}

// Вывод оценки (только чтение).
export function StarDisplay({ value, className = "" }: { value: number; className?: string }) {
  return (
    <span className={`inline-flex gap-0.5 ${className}`} aria-label={`Оценка ${value} из 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          className={n <= value ? "h-4 w-4 fill-amber-400 text-amber-400" : "h-4 w-4 text-ink-3"}
          aria-hidden
        />
      ))}
    </span>
  );
}
