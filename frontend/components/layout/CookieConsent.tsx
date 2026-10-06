"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";

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

const NAV_SELECTOR = 'nav[aria-label="Мобильная навигация"]';
/** Маршруты с собственным нижним баром действий (72px): корзина, товар, чекаут. */
function hasActionBar(pathname: string): boolean {
  return (
    pathname.startsWith("/cart") ||
    pathname.startsWith("/product/") ||
    pathname.startsWith("/checkout")
  );
}
const ACTION_BAR_PX = 72;
const EDGE_PX = 12;

export function CookieConsent({ initialConsent }: { initialConsent: Consent | null }) {
  const pathname = usePathname() ?? "/";
  const consent = useConsent(initialConsent);
  // Карточка открыта, пока выбора нет, либо пока её открыли кнопкой «Настройки cookie».
  const [reopened, setReopened] = useState(false);
  const titleId = useId();
  const cardRef = useRef<HTMLElement | null>(null);

  // Отступ снизу на мобильном считаем по факту, а не по маршруту: мобильная
  // навигация (64px) есть не на всех страницах (на главной её нет), а бар
  // «В корзину»/«Оформить» на товаре, в корзине и чекауте — 72px. Пишем в CSS-переменную
  // прямо на элемент, без состояния: это измерение DOM, а не данные. На lg класс
  // lg:bottom-6 перекрывает переменную — там панелей нет.
  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const nav = document.querySelector<HTMLElement>(NAV_SELECTOR);
    const navPx = nav && getComputedStyle(nav).display !== "none" ? nav.offsetHeight : 0;
    const barPx = hasActionBar(pathname) ? ACTION_BAR_PX : 0;
    el.style.setProperty("--cc-offset", `${navPx + barPx + EDGE_PX}px`);
  });

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
      ref={cardRef}
      className={cn(
        // z-[45]: над sticky-барами товара и корзины (z-40), под мобильной навигацией,
        // панелью чекаута (z-50) и модальными окнами.
        "fixed left-3 right-3 z-[45] max-w-[530px] rounded-xl bg-surface p-5 text-left",
        "bottom-[calc(var(--cc-offset,12px)_+_env(safe-area-inset-bottom))] lg:bottom-6",
        "shadow-[0_12px_40px_rgba(20,24,27,0.16)] ring-1 ring-black/5 sm:left-6 sm:right-auto sm:w-[530px] sm:p-7",
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

      <div className="mt-5 grid grid-cols-1 gap-3 min-[420px]:grid-cols-2">
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
