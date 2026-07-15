"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { pluralize } from "@/lib/format";

// Полноэкранный drawer фильтров для мобильных (§4): Escape закрывает, фокус
// возвращается на кнопку-триггер, кнопка применения закреплена снизу, зоны нажатия
// ≥44px. Состав фильтров — children (тот же FacetSidebar, что и на десктопе).
export function MobileFilterDrawer({
  open,
  onClose,
  total,
  onReset,
  triggerRef,
  chips,
  children,
}: {
  open: boolean;
  onClose: () => void;
  total: number;
  onReset: () => void;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
  chips: { key: string; label: string; onRemove: () => void }[];
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    // блокируем скролл фона + вешаем Escape и простой фокус-трап
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      // §4: вернуть фокус на кнопку «Фильтры», открывшую drawer
      trigger?.focus();
    };
  }, [open, onClose, triggerRef]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button
        type="button"
        aria-label="Закрыть фильтры"
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Фильтры"
        className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-canvas"
      >
        <div className="flex min-h-14 items-center justify-between gap-4 border-b border-line px-4">
          <h2 className="text-lg font-bold text-ink">Фильтры</h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onReset}
              className="min-h-11 px-2 text-sm font-medium text-accent"
            >
              Сбросить всё
            </button>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Закрыть"
              className="grid h-11 w-11 place-items-center rounded-md text-ink-2 hover:bg-raised"
            >
              <X className="h-5 w-5" aria-hidden />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {chips.length > 0 && (
            <div className="mb-4 flex flex-wrap gap-2">
              {chips.map((c) => (
                <button
                  key={c.key}
                  type="button"
                  onClick={c.onRemove}
                  className="inline-flex min-h-9 items-center gap-2 rounded-md border border-accent/40 bg-accent/5 px-3 text-sm text-accent"
                >
                  {c.label}
                  <X className="h-3.5 w-3.5" aria-hidden />
                </button>
              ))}
            </div>
          )}
          {children}
        </div>

        <div className="border-t border-line p-4">
          <button
            type="button"
            onClick={onClose}
            className="min-h-12 w-full rounded-md bg-accent px-4 font-bold text-accent-ink"
          >
            Показать {total} {pluralize(total, "товар", "товара", "товаров")}
          </button>
        </div>
      </div>
    </div>
  );
}
