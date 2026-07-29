"use client";

import { useState } from "react";
import { BarChart3 } from "lucide-react";

import { COMPARE_LIMIT, useCompare } from "@/lib/compare";
import { cn } from "@/lib/utils";

/**
 * Кнопка «добавить к сравнению».
 *
 * ``variant="icon"`` — для плитки каталога (рядом с сердцем), ``"wide"`` — для
 * страницы товара, где есть место на подпись.
 *
 * Отказ по лимиту показываем текстом рядом с кнопкой: молча ничего не делать —
 * худший вариант, человек решит, что сайт сломан.
 */
export function CompareButton({
  slug,
  variant = "icon",
  className,
}: {
  slug: string;
  variant?: "icon" | "wide";
  className?: string;
}) {
  const { has, toggle } = useCompare();
  const [rejected, setRejected] = useState(false);
  const active = has(slug);

  const onClick = () => {
    const ok = toggle(slug);
    setRejected(!ok);
  };

  const label = active ? "Убрать из сравнения" : "Добавить к сравнению";

  if (variant === "wide") {
    return (
      <div className={className}>
        <button
          type="button"
          onClick={onClick}
          aria-pressed={active}
          data-event="compare_toggle"
          className={cn(
            "inline-flex h-11 items-center gap-2 rounded-md border px-4 text-sm font-medium transition",
            active
              ? "border-accent bg-accent/5 text-accent"
              : "border-line text-ink-2 hover:border-accent hover:text-accent",
          )}
        >
          <BarChart3 className="h-4 w-4" aria-hidden />
          {active ? "В сравнении" : "Сравнить"}
        </button>
        {rejected && (
          <p className="mt-1 text-xs text-ink-3">
            В сравнении уже {COMPARE_LIMIT} товара — уберите один, чтобы добавить этот.
          </p>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
      title={rejected ? `Можно сравнивать не больше ${COMPARE_LIMIT} товаров` : label}
      data-event="compare_toggle"
      className={cn(
        // #478: на мобильном hit-area ≥44px, на десктопе кнопка компактная.
        "grid h-11 w-11 shrink-0 place-items-center rounded-full transition-colors sm:h-8 sm:w-8",
        active ? "text-accent" : "text-ink-3 hover:text-accent",
        rejected && "text-danger",
        className,
      )}
    >
      <BarChart3 className="h-4 w-4" aria-hidden />
    </button>
  );
}
