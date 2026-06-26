"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// Сворачиваемый блок с кнопкой «Показать всё»/«Свернуть» и градиентным затемнением
// в свёрнутом виде. Решение «нужно ли сворачивать» принимает родитель (по длине
// контента) — здесь тоггл показывается всегда.
export function Collapsible({
  children,
  collapsedHeight = 240,
  moreLabel = "Показать всё",
  lessLabel = "Свернуть",
}: {
  children: React.ReactNode;
  collapsedHeight?: number;
  moreLabel?: string;
  lessLabel?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <div
        className="relative overflow-hidden"
        style={open ? undefined : { maxHeight: collapsedHeight }}
      >
        {children}
        {!open && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-surface to-transparent" />
        )}
      </div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
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
