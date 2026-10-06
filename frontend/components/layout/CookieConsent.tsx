"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";

import { CONSENT_OPEN_EVENT, writeConsent, type Consent } from "@/lib/cookie-consent";
import { useConsent } from "@/lib/use-consent";
import { cn } from "@/lib/utils";

// Баннер согласия на cookie (DRF-2796), макет владельца от 06.10.2026: компактная
// карточка в левом нижнем углу, заголовок, две строки текста, ссылка на политику и
// ровно две кнопки — «Только необходимые» (серая) и «Принять все» (зелёная).
//
// Не модальное окно: страница читается и прокручивается, фокус не захватывается,
// затемнения нет. Категория у сайта одна необязательная (аналитика), поэтому
// отдельного «Настроить» в карточке нет: любой из двух ответов и есть настройка.
// Изменить выбор можно кнопкой «Настройки cookie» в подвале и на странице политики —
// она открывает эту же карточку заново.
//
// Решение известно уже на сервере (layout читает cookie и передаёт initialConsent):
// у ответившего карточка не мигает при загрузке. Срок хранения выбора — 12 месяцев,
// см. lib/cookie-consent.ts.

export const CONSENT_TITLE = "Используем cookie";
export const CONSENT_TEXT_LINES = [
  "Для работы корзины и входа на сайт.",
  "Аналитика помогает улучшать магазин — только с вашего согласия.",
] as const;

function bottomOffset(pathname: string): string {
  // На мобильном внизу уже стоят панели: навигация (64px) везде, над ней — бар
  // «В корзину»/«Оформить» на товаре и в корзине (72px); на чекауте своя панель
  // (72px) без навигации. Карточка встаёт над ними, а не поверх кнопок. На товаре
  // бар появляется после прокрутки за блок покупки — до этого под карточкой
  // 72px пустоты; сознательный компромисс ради кнопок бара. С lg панелей нет.
  if (pathname.startsWith("/checkout")) return "bottom-[calc(72px_+_12px)] lg:bottom-6";
  if (pathname.startsWith("/cart") || pathname.startsWith("/product/")) {
    return "bottom-[calc(136px_+_12px)] lg:bottom-6";
  }
  return "bottom-[calc(64px_+_12px_+_env(safe-area-inset-bottom))] lg:bottom-6";
}

export function CookieConsent({ initialConsent }: { initialConsent: Consent | null }) {
  const pathname = usePathname() ?? "/";
  const consent = useConsent(initialConsent);
  // Карточка открыта, пока выбора нет, либо пока её открыли кнопкой «Настройки cookie».
  const [reopened, setReopened] = useState(false);
  const titleId = useId();

  useEffect(() => {
    const onOpen = () => setReopened(true);
    window.addEventListener(CONSENT_OPEN_EVENT, onOpen);
    return () => window.removeEventListener(CONSENT_OPEN_EVENT, onOpen);
  }, []);

  const decide = useCallback((analytics: boolean) => {
    writeConsent({ analytics });
    setReopened(false);
  }, []);

  if (consent !== null && !reopened) return null;

  return (
    <section
      role="region"
      aria-labelledby={titleId}
      data-testid="cookie-consent"
      className={cn(
        // z-[45]: над sticky-барами товара и корзины (z-40), под мобильной навигацией,
        // панелью чекаута (z-50) и модальными окнами.
        "fixed left-3 right-3 z-[45] max-w-[530px] rounded-xl bg-surface p-5 text-left",
        "shadow-[0_12px_40px_rgba(20,24,27,0.16)] ring-1 ring-black/5 sm:left-6 sm:right-auto sm:w-[530px] sm:p-7",
        bottomOffset(pathname),
      )}
    >
      <h2 id={titleId} className="text-xl font-bold leading-tight text-ink sm:text-[22px]">
        {CONSENT_TITLE}
      </h2>
      <p className="mt-2 text-base leading-6 text-ink-2">
        {CONSENT_TEXT_LINES[0]}
        <br />
        {CONSENT_TEXT_LINES[1]}
      </p>
      <Link
        href="/info/privacy"
        className="mt-2 inline-block text-base leading-6 text-ink-2 underline underline-offset-4 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
      >
        Политика конфиденциальности
      </Link>

      <div className="mt-5 grid grid-cols-1 gap-3 min-[360px]:grid-cols-2">
        <button
          type="button"
          onClick={() => decide(false)}
          className="h-12 rounded-lg bg-raised px-4 text-base font-medium text-ink transition-colors hover:bg-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
        >
          Только необходимые
        </button>
        <button
          type="button"
          onClick={() => decide(true)}
          className="h-12 rounded-lg bg-accent px-4 text-base font-medium text-accent-ink transition hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
        >
          Принять все
        </button>
      </div>
    </section>
  );
}
