"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { Check, X } from "lucide-react";
import { dismissCopyToast, getCopyToast, subscribeCopyToast } from "./copy-toast";

// Регион уведомлений о копировании — один на страницу (монтируется в layout).
// Контейнер с aria-live стоит в разметке ВСЕГДА, а меняется только содержимое:
// скринридеры не объявляют регион, который появился уже с текстом внутри.
export function CopyToastRegion() {
  const toast = useSyncExternalStore(subscribeCopyToast, getCopyToast, () => null);
  const manualRef = useRef<HTMLInputElement>(null);

  // Ручной режим: сразу выделяем текст — остаётся нажать Ctrl+C / «Копировать».
  useEffect(() => {
    if (toast?.kind !== "manual") return;
    manualRef.current?.focus();
    manualRef.current?.select();
  }, [toast]);

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="pointer-events-none fixed inset-x-0 bottom-20 z-[70] flex justify-center px-4 lg:bottom-6"
    >
      {toast && (
        <div
          key={toast.id}
          role={toast.kind === "manual" ? "alert" : "status"}
          className="pointer-events-auto flex max-w-md items-start gap-3 rounded-lg border border-line bg-expert px-4 py-3 text-sm text-expert-ink shadow-lg"
        >
          {toast.kind === "success" ? (
            <>
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
              <span>{toast.message}</span>
            </>
          ) : (
            <span className="flex min-w-0 flex-col gap-2">
              <span>{toast.message}</span>
              <input
                ref={manualRef}
                readOnly
                value={toast.value}
                aria-label="Текст для копирования вручную"
                onFocus={(event) => event.currentTarget.select()}
                className="h-11 w-full min-w-0 rounded-md border border-white/25 bg-white/10 px-3 text-base text-expert-ink outline-none"
              />
            </span>
          )}
          <button
            type="button"
            onClick={dismissCopyToast}
            aria-label="Закрыть уведомление"
            className="-mr-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-expert-ink/70 transition hover:text-expert-ink"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
      )}
    </div>
  );
}
