"use client";

import { Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

// Контролируемый счётчик количества для блока покупки. Презентационный: не знает
// о корзине, только сообщает наружу новое значение через onChange. Кламп в [min, max].
export function QuantityStepper({
  value,
  max,
  min = 1,
  onChange,
  disabled = false,
  id,
}: {
  value: number;
  max?: number;
  min?: number;
  onChange: (next: number) => void;
  disabled?: boolean;
  id?: string;
}) {
  const clamp = (n: number) => {
    if (Number.isNaN(n)) return min;
    const lo = Math.max(min, n);
    return max != null ? Math.min(max, lo) : lo;
  };

  const set = (n: number) => onChange(clamp(n));

  return (
    <div className={cn("inline-flex items-center rounded-md border border-line bg-surface")}>
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center text-ink-2 hover:text-ink disabled:opacity-40"
        onClick={() => set(value - 1)}
        disabled={disabled || value <= min}
        aria-label="Уменьшить количество"
      >
        <Minus className="h-4 w-4" aria-hidden />
      </button>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        className="h-9 w-12 bg-transparent text-center text-sm text-ink outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
        value={value}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => set(parseInt(e.target.value, 10))}
        aria-label="Количество"
      />
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center text-ink-2 hover:text-ink disabled:opacity-40"
        onClick={() => set(value + 1)}
        disabled={disabled || (max != null && value >= max)}
        aria-label="Увеличить количество"
      >
        <Plus className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
