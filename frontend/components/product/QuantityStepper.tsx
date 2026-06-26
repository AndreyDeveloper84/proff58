"use client";

import { useState } from "react";
import { Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

// Контролируемый счётчик количества для блока покупки. Презентационный: не знает
// о корзине, только сообщает наружу новое значение через onChange. Кламп в [min, max].
// Локальный «черновик» ввода: пока пользователь печатает, поле может быть пустым/частичным
// и не сбрасывается в min (нормализация — на blur).
//
// Паттерн синхронизации: state хранит пару {committed, draft}.
// Если входящий value расходится с committed — внешний источник изменил значение,
// черновик сбрасывается немедленно в том же рендере (без useEffect / ref в render).
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

  // committed — последнее значение, которое компонент «принял» как своё.
  // draft — текущее содержимое поля (строка, может быть пустой или частичной).
  const [{ committed, draft }, setState] = useState({
    committed: value,
    draft: String(value),
  });

  // Derived-state: если prop value изменился снаружи — сбрасываем черновик.
  // Это допустимо в теле функции компонента (не в эффекте).
  const displayDraft = committed !== value ? String(value) : draft;
  const displayCommitted = committed !== value ? value : committed;

  const commit = (n: number) => {
    const v = clamp(n);
    onChange(v);
    setState({ committed: v, draft: String(v) });
  };

  return (
    <div className={cn("inline-flex items-center rounded-md border border-line bg-surface")}>
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center text-ink-2 hover:text-ink disabled:opacity-40"
        onClick={() => commit(value - 1)}
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
        value={displayDraft}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => {
          const raw = e.target.value;
          setState({ committed: displayCommitted, draft: raw });
          if (raw !== "") {
            const n = parseInt(raw, 10);
            if (!Number.isNaN(n)) onChange(clamp(n));
          }
        }}
        onBlur={() => commit(parseInt(displayDraft, 10))}
        aria-label="Количество"
      />
      <button
        type="button"
        className="flex h-9 w-9 items-center justify-center text-ink-2 hover:text-ink disabled:opacity-40"
        onClick={() => commit(value + 1)}
        disabled={disabled || (max != null && value >= max)}
        aria-label="Увеличить количество"
      >
        <Plus className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
