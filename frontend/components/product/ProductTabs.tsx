"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type ProductTabId = "overview" | "characteristics" | "description";

export type ProductTab = {
  id: ProductTabId;
  label: string;
  /** Серверный контент панели: рендерится один раз и дальше только прячется. */
  content: ReactNode;
};

// Все id, которые считаются «хэшем вкладки», — даже если у товара такой вкладки нет.
// Хэш отсутствующей вкладки (#description у товара без описания) открывает «О товаре»;
// любой другой хэш (#reviews, #compatible) принадлежит странице, и вкладку он не трогает.
const TAB_HASHES: readonly ProductTabId[] = ["overview", "characteristics", "description"];

function readTabHash(): ProductTabId | null {
  const raw = window.location.hash.slice(1);
  return (TAB_HASHES as readonly string[]).includes(raw) ? (raw as ProductTabId) : null;
}

/**
 * Вкладки карточки товара «О товаре / Характеристики / Описание».
 *
 * Раньше это были якоря в длинной ленте: клик прокручивал страницу, а подсветка
 * стояла на «О товаре» всегда. Теперь видна ровно одна панель — одно состояние
 * `active`, поэтому быстрые клики в любом порядке не оставят две открытыми.
 * Неактивные панели остаются в DOM с `hidden`: серверный контент не дублируется
 * и не перемонтируется при переключении (раскрытый «Показать всё» сохраняется).
 *
 * Хэш обновляется через `history.replaceState` — без прыжка страницы и без новой
 * записи в истории. Первый рендер всегда «О товаре» (сервер хэша не видит), нужная
 * вкладка по прямому URL включается уже после гидратации.
 */
export function ProductTabs({ tabs, extraLinks }: { tabs: ProductTab[]; extraLinks?: ReactNode }) {
  const defaultId: ProductTabId = tabs.some((t) => t.id === "overview")
    ? "overview"
    : (tabs[0]?.id ?? "overview");
  const [active, setActive] = useState<ProductTabId>(defaultId);
  const tablistRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef(new Map<ProductTabId, HTMLButtonElement>());
  // Последний обработанный хэш: переход по ссылке-якорю шлёт и popstate, и hashchange —
  // без этой отметки страница прокручивалась бы к вкладкам дважды.
  const handledHash = useRef<string | null>(null);

  const idsKey = tabs.map((t) => t.id).join(",");

  useEffect(() => {
    const ids = idsKey.split(",") as ProductTabId[];

    // Открыть вкладку по хэшу. Браузер к hidden-панели сам не прокрутит, поэтому
    // полосу вкладок (у неё scroll-mt под липкую шапку) показываем вручную.
    const syncFromHash = (scroll: boolean) => {
      const hash = window.location.hash;
      if (hash === handledHash.current) return;
      handledHash.current = hash;
      const fromHash = readTabHash();
      if (!fromHash) return; // чужой хэш — вкладку не сбрасываем
      const target = ids.includes(fromHash) ? fromHash : defaultId;
      setActive(target);
      if (scroll) tablistRef.current?.scrollIntoView({ block: "start" });
    };

    // При монтировании прокручиваем только к вкладке, которая действительно есть:
    // #description у товара без описания молча оставляет «О товаре» и страницу на месте.
    const initial = readTabHash();
    syncFromHash(initial != null && ids.includes(initial));

    const onNavigate = () => syncFromHash(true);
    window.addEventListener("hashchange", onNavigate);
    window.addEventListener("popstate", onNavigate);
    return () => {
      window.removeEventListener("hashchange", onNavigate);
      window.removeEventListener("popstate", onNavigate);
    };
  }, [idsKey, defaultId]);

  const activate = useCallback((id: ProductTabId, focus: boolean) => {
    setActive(id);
    if (focus) tabRefs.current.get(id)?.focus();
    const hash = `#${id}`;
    handledHash.current = hash;
    if (window.location.hash !== hash) {
      // state = null — так, как велит документация Next: App Router сам
      // переносит свои служебные поля и сверяет URL роутера. С чужим state (где
      // уже есть __NA) он пропускает синхронизацию, и хэш потом терялся бы при
      // первом router.refresh().
      window.history.replaceState(null, "", hash);
    }
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.findIndex((t) => t.id === active);
    let next: number;
    switch (event.key) {
      case "ArrowRight":
        next = (index + 1) % tabs.length;
        break;
      case "ArrowLeft":
        next = (index - 1 + tabs.length) % tabs.length;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = tabs.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    activate(tabs[next].id, true);
  };

  return (
    <section className="mt-8 overflow-hidden rounded-lg border border-line bg-surface">
      {/* Полоса прокручивается по горизонтали сама, не растягивая страницу на 320 px. */}
      <div className="flex min-w-0 gap-6 overflow-x-auto border-b border-line bg-surface px-4 text-sm font-semibold text-ink-2 sm:px-5">
        <div
          ref={tablistRef}
          role="tablist"
          aria-label="Разделы карточки товара"
          onKeyDown={onKeyDown}
          className="flex shrink-0 scroll-mt-28 gap-6"
        >
          {tabs.map((tab) => {
            const selected = tab.id === active;
            return (
              <button
                key={tab.id}
                ref={(node) => {
                  if (node) tabRefs.current.set(tab.id, node);
                  else tabRefs.current.delete(tab.id);
                }}
                type="button"
                role="tab"
                id={`tab-${tab.id}`}
                aria-selected={selected}
                aria-controls={tab.id}
                tabIndex={selected ? 0 : -1}
                onClick={() => activate(tab.id, false)}
                className={cn(
                  // Кольцо фокуса внутрь: наружный outline обрезала бы прокручиваемая полоса.
                  "min-h-12 shrink-0 border-b-2 py-3.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent",
                  selected ? "border-accent text-ink" : "border-transparent hover:text-accent",
                )}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
        {extraLinks && <div className="ml-auto flex shrink-0 gap-6">{extraLinks}</div>}
      </div>

      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={tab.id}
          aria-labelledby={`tab-${tab.id}`}
          tabIndex={0}
          hidden={tab.id !== active}
          className="bg-raised p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent sm:p-5 lg:p-6"
        >
          {tab.content}
        </div>
      ))}
    </section>
  );
}
