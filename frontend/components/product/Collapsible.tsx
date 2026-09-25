"use client";

import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// Сворачиваемый блок с кнопкой «Показать всё»/«Свернуть» и градиентным затемнением
// в свёрнутом виде. Решение «нужно ли сворачивать» принимает родитель (по длине
// контента) — здесь тоггл показывается всегда.
//
// fade — фон, в который уходит затемнение: цвет того, на чём блок лежит. Градиент
// from-surface поверх панели bg-raised давал заметную полосу, особенно в тёмной теме.
// Классы перечислены целиком, чтобы Tailwind их увидел.
const FADE = {
  surface: "from-surface",
  raised: "from-raised",
} as const;

export function Collapsible({
  children,
  collapsedHeight = 240,
  moreLabel = "Показать всё",
  lessLabel = "Свернуть",
  fade = "surface",
}: {
  children: React.ReactNode;
  collapsedHeight?: number;
  moreLabel?: string;
  lessLabel?: string;
  fade?: keyof typeof FADE;
}) {
  const [open, setOpen] = useState(false);
  const regionId = useId();

  return (
    <div>
      <div
        id={regionId}
        className="relative overflow-hidden"
        style={open ? undefined : { maxHeight: collapsedHeight }}
      >
        {children}
        {!open && (
          <div
            className={cn(
              "pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t to-transparent",
              FADE[fade],
            )}
          />
        )}
      </div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={regionId}
        className="mt-2 inline-flex items-center gap-1 text-sm text-accent hover:underline"
      >
        {open ? lessLabel : moreLabel}
        <ChevronDown
          className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>
    </div>
  );
}
