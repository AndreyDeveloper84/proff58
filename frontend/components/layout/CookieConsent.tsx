"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  CONSENT_OPEN_EVENT,
  readConsent,
  useConsent,
  writeConsent,
  type Consent,
} from "@/lib/cookie-consent";
import { cn } from "@/lib/utils";

// Баннер согласия на cookie (DRF-2796).
//
// Не модальное окно: панель внизу, страница читается и прокручивается, фокус не
// захватывается. «Принять все» и «Только необходимые» — одинаковые кнопки в одном
// ряду, чтобы отказ не был спрятан. «Настроить» раскрывает категории: необходимые
// без переключателя (без них сайт не работает), аналитические — переключатель.
//
// Решение известно уже на сервере (layout читает cookie и передаёт initialConsent):
// у согласившегося баннер не мигает при загрузке. Текст — рабочий, до юриста
// (срок хранения выбора 12 месяцев, см. lib/cookie-consent.ts).

export const CONSENT_TEXT =
  "Мы используем cookie: необходимые — для работы корзины и входа, аналитические — чтобы " +
  "понимать, как пользуются сайтом (Яндекс.Метрика). Аналитика включается только с вашего " +
  "согласия. Выбор можно изменить в любой момент в подвале сайта.";

function bottomOffset(pathname: string): string {
  // На мобильном внизу уже стоят панели: навигация (64px) везде, над ней — бар
  // «В корзину»/«Оформить» на товаре и в корзине (72px); на чекауте своя панель
  // (72px) без навигации. Баннер встаёт над ними, а не поверх кнопок.
  if (pathname.startsWith("/checkout")) return "bottom-[72px] lg:bottom-0";
  // На товаре бар появляется после прокрутки за блок покупки; до этого под баннером
  // 72px пустоты над навигацией — сознательный компромисс ради кнопок бара.
  if (pathname.startsWith("/cart") || pathname.startsWith("/product/")) {
    return "bottom-[136px] lg:bottom-0";
  }
  return "bottom-[64px] lg:bottom-0";
}

export function CookieConsent({ initialConsent }: { initialConsent: Consent | null }) {
  const pathname = usePathname() ?? "/";
  const consent = useConsent(initialConsent);
  // Баннер открыт, пока выбора нет, либо пока его открыли кнопкой «Настройки cookie».
  const [reopened, setReopened] = useState(false);
  const [customize, setCustomize] = useState(false);
  const [analytics, setAnalytics] = useState(initialConsent?.analytics ?? false);
  const descriptionId = useId();
  const switchId = useId();
  const analyticsDescId = useId();

  useEffect(() => {
    const onOpen = () => {
      // Переключатель показывает текущий выбор, а не прошлое состояние формы.
      setAnalytics(readConsent()?.analytics ?? false);
      setCustomize(true);
      setReopened(true);
    };
    window.addEventListener(CONSENT_OPEN_EVENT, onOpen);
    return () => window.removeEventListener(CONSENT_OPEN_EVENT, onOpen);
  }, []);

  // Переключатель при открытии показывает текущий выбор, а не прошлое состояние формы.
  const openCustomize = useCallback(() => {
    setAnalytics(consent?.analytics ?? false);
    setCustomize(true);
  }, [consent]);

  const decide = useCallback((value: boolean) => {
    writeConsent({ analytics: value });
    setAnalytics(value);
    setCustomize(false);
    setReopened(false);
  }, []);

  if (consent !== null && !reopened) return null;

  return (
    <section
      role="region"
      aria-label="Согласие на cookie"
      aria-describedby={descriptionId}
      data-testid="cookie-consent"
      className={cn(
        "fixed inset-x-0 z-[45] border-t border-line bg-surface px-4 py-3 shadow-[0_-8px_24px_rgba(20,24,27,0.08)] sm:px-6",
        bottomOffset(pathname),
      )}
    >
      <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-3 lg:flex-row lg:items-center lg:justify-between xl:px-2">
        <p id={descriptionId} className="text-sm leading-snug text-ink-2">
          {CONSENT_TEXT}{" "}
          <Link href="/info/privacy" className="text-accent hover:underline">
            Политика конфиденциальности
          </Link>
        </p>

        <div className="flex flex-col gap-3 lg:shrink-0">
          {customize && (
            <ul className="space-y-2 text-sm">
              <li className="flex items-center justify-between gap-4">
                <span>
                  <span className="font-medium text-ink">Необходимые</span>
                  <span className="block text-xs text-ink-3">
                    Сессия, корзина, вход, защита форм, запись этого выбора. Всегда включены.
                  </span>
                </span>
                <span className="text-xs text-ink-3">Всегда</span>
              </li>
              <li className="flex items-center justify-between gap-4">
                <span>
                  <label htmlFor={switchId} className="font-medium text-ink">
                    Аналитические
                  </label>
                  <span id={analyticsDescId} className="block text-xs text-ink-3">
                    Яндекс.Метрика: какие страницы смотрят и что нажимают, без ваших данных.
                  </span>
                </span>
                <Switch
                  id={switchId}
                  checked={analytics}
                  onChange={setAnalytics}
                  describedBy={analyticsDescId}
                />
              </li>
            </ul>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {customize ? (
              <Button type="button" variant="accent" size="sm" onClick={() => decide(analytics)}>
                Сохранить выбор
              </Button>
            ) : (
              <>
                <Button type="button" variant="outline" size="sm" onClick={() => decide(true)}>
                  Принять все
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => decide(false)}>
                  Только необходимые
                </Button>
                <button
                  type="button"
                  onClick={openCustomize}
                  className="min-h-11 px-2 text-sm text-ink-2 hover:text-accent hover:underline sm:min-h-0"
                >
                  Настроить
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
