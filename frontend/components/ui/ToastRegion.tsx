"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { dismissToast, getToast, pauseToast, resumeToast, subscribeToast } from "@/lib/toast";

/**
 * Регион всплывающих уведомлений — один на страницу (монтируется в layout).
 *
 * Доступность:
 * - live-область (`aria-live="polite"`) стоит в разметке ВСЕГДА, меняется только её
 *   содержимое: скринридеры не объявляют регион, появившийся уже с текстом внутри;
 * - внутри live-области — только текст сообщения. У сообщения нет своего role
 *   (status/alert внутри polite-региона дали бы двойное озвучивание), а кнопка
 *   «Закрыть уведомление» и поле ручного копирования стоят рядом, вне области,
 *   чтобы их подписи не зачитывались вместе с сообщением.
 *
 * Положение: fixed — контент не сдвигается. На телефоне и планшете — сверху под
 * sticky-шапкой (снизу там нижняя навигация и панель оформления корзины), на lg —
 * снизу по центру. Клики принимает только сама карточка.
 *
 * Пока курсор или фокус на карточке, таймер стоит; уходят оба — досчитывается остаток.
 */
export function ToastRegion() {
  const toast = useSyncExternalStore(subscribeToast, getToast, () => null);
  const manualRef = useRef<HTMLInputElement>(null);
  const hovered = useRef(false);
  const focused = useRef(false);

  // Новое сообщение сбрасывает паузу в сторе — сбрасываем и локальные флаги, иначе
  // «залипший» hover от прежней карточки не дал бы досчитать таймер.
  const toastId = toast?.id;
  useEffect(() => {
    hovered.current = false;
    focused.current = false;
  }, [toastId]);

  // Ручной режим: сразу выделяем текст — остаётся нажать Ctrl+C / «Копировать».
  useEffect(() => {
    if (toast?.kind !== "manual") return;
    manualRef.current?.focus();
    manualRef.current?.select();
  }, [toast]);

  const resumeIfIdle = () => {
    if (!hovered.current && !focused.current) resumeToast();
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 top-[76px] z-[70] flex justify-center px-4 lg:bottom-6 lg:top-auto">
      <div
        data-testid="toast-card"
        onMouseEnter={() => {
          hovered.current = true;
          pauseToast();
        }}
        onMouseLeave={() => {
          hovered.current = false;
          resumeIfIdle();
        }}
        onFocus={() => {
          focused.current = true;
          pauseToast();
        }}
        onBlur={(event) => {
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
          focused.current = false;
          resumeIfIdle();
        }}
        className={cn(
          toast &&
            "pointer-events-auto flex max-w-md items-start gap-3 rounded-lg border border-line bg-expert px-4 py-3 text-sm text-expert-ink shadow-lg",
        )}
      >
        {toast?.kind === "success" && (
          <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
        )}
        <div className="flex min-w-0 flex-col gap-2">
          <div aria-live="polite" aria-atomic="true" data-testid="toast-live">
            {/* key: повтор того же текста — это новое событие, его тоже нужно объявить. */}
            {toast && <span key={toast.id}>{toast.message}</span>}
          </div>
          {toast?.kind === "manual" && (
            <input
              ref={manualRef}
              readOnly
              value={toast.value}
              aria-label="Текст для копирования вручную"
              onFocus={(event) => event.currentTarget.select()}
              className="h-11 w-full min-w-0 rounded-md border border-white/25 bg-white/10 px-3 text-base text-expert-ink outline-none"
            />
          )}
        </div>
        {toast && (
          <button
            type="button"
            onClick={dismissToast}
            aria-label="Закрыть уведомление"
            className="-mr-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-expert-ink/70 transition hover:text-expert-ink"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}
