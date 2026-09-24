"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LayoutGrid, Search, X } from "lucide-react";
import { ProductAvailability } from "@/components/product/ProductAvailability";
import { ProductImage } from "@/components/product/ProductImage";
import { apiProductToProduct, type ApiProduct } from "@/lib/adapters";
import { formatPrice, pluralize } from "@/lib/format";
import type { Product } from "@/lib/types";
import { cn } from "@/lib/utils";

// Быстрый поиск в шапке: combobox по WAI-ARIA 1.2 (фокус остаётся в поле, активная
// опция — через aria-activedescendant). Данные — same-origin BFF GET /api/search/quick?q=
// → Django SearchQuickView: до 3 разделов (категория + вид товара) и до 6 карточек.

type QuickCategory = {
  name: string;
  category: { name: string; slug: string };
  tool_type: string | null;
};

type QuickResult = { products: Product[]; categories: QuickCategory[] };

type QuickResponse = {
  products?: ApiProduct[];
  categories?: QuickCategory[];
};

// Ответ, привязанный к нормализованному запросу: панель показывает его, только пока
// поле содержит тот же текст, — поздний ответ на старый запрос не «перебьёт» новый.
type Entry = { key: string; data?: QuickResult; error?: boolean };

type Option =
  | { kind: "category"; id: string; href: string; item: QuickCategory }
  | { kind: "product"; id: string; href: string; item: Product }
  | { kind: "all"; id: string; href: string };

const MIN_QUERY = 2;
const DEBOUNCE_MS = 275;
const CACHE_LIMIT = 30;

const normalize = (value: string) => value.trim().toLowerCase();

const searchHref = (q: string) => `/search?q=${encodeURIComponent(q.trim())}`;

function categoryHref(c: QuickCategory): string {
  const base = `/catalog/${encodeURIComponent(c.category.slug)}`;
  return c.tool_type ? `${base}?tool_type=${encodeURIComponent(c.tool_type)}` : base;
}

// Строка-опция listbox. Фокус остаётся в поле: mousedown не уводит его из input,
// иначе blur закрыл бы панель раньше клика (и на тапе по телефону тоже).
function OptionRow({
  id,
  selected,
  onSelect,
  onHover,
  className,
  children,
}: {
  id: string;
  selected: boolean;
  onSelect: () => void;
  onHover: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <li
      id={id}
      role="option"
      aria-selected={selected}
      onMouseDown={(e) => e.preventDefault()}
      onMouseEnter={onHover}
      onClick={onSelect}
      className={cn("cursor-pointer hover:bg-surface aria-selected:bg-surface", className)}
    >
      {children}
    </li>
  );
}

export function SearchBar({
  className,
  placeholder = "Поиск товаров…",
  initialQuery = "",
}: {
  className?: string;
  placeholder?: string;
  /** Начальный текст — страница поиска подставляет сюда текущий запрос. */
  initialQuery?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const baseId = useId();
  const listboxId = `${baseId}-listbox`;

  const [query, setQuery] = useState(initialQuery);
  const [open, setOpen] = useState(false);
  const [entry, setEntry] = useState<Entry | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  // Смена адреса закрывает панель (переход по ссылке шапки, «назад» браузера).
  // Сравнение во время рендера, а не эффект: так React советует сбрасывать состояние
  // по смене пропа, и лишнего кадра с открытой панелью на новой странице нет.
  const [seenPathname, setSeenPathname] = useState(pathname);
  if (seenPathname !== pathname) {
    setSeenPathname(pathname);
    setOpen(false);
    setActiveIndex(-1);
  }

  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Прерываем устаревший запрос, чтобы поздний ответ не тратил сеть и не «перебил» свежий.
  const abortRef = useRef<AbortController | null>(null);
  const inflightKeyRef = useRef<string | null>(null);
  // Кэш ответов на время жизни компонента: повторный ввод того же текста (стёр букву и
  // вернул) не отправляет запрос. Map хранит порядок вставки — старые вытесняем первыми.
  const cacheRef = useRef<Map<string, QuickResult>>(new Map());
  // Нажатие внутри поиска (тап по опции на телефоне): часть мобильных браузеров снимает
  // фокус с поля до click, и blur закрыл бы панель вместе с опцией раньше выбора.
  const pointerInsideRef = useRef(false);

  const key = normalize(query);
  const active = key.length >= MIN_QUERY;
  const current = entry && entry.key === key ? entry : null;
  const loading = active && !current;
  const result = current?.data;
  const failed = Boolean(current?.error);
  const empty = Boolean(result && !result.products.length && !result.categories.length);

  const options: Option[] = [];
  if (result) {
    result.categories.forEach((item, i) =>
      options.push({ kind: "category", id: `${baseId}-cat-${i}`, href: categoryHref(item), item }),
    );
    result.products.forEach((item) =>
      options.push({
        kind: "product",
        id: `${baseId}-product-${item.id}`,
        href: `/product/${item.slug}`,
        item,
      }),
    );
  }
  if (active) options.push({ kind: "all", id: `${baseId}-all`, href: searchHref(query) });

  const expanded = open && active;
  const activeOption = expanded && activeIndex >= 0 ? options[activeIndex] : undefined;

  const cancelPending = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = null;
  }, []);

  const abortInflight = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    inflightKeyRef.current = null;
  }, []);

  const fetchQuick = useCallback(async (text: string, k: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    inflightKeyRef.current = k;
    try {
      const res = await fetch(`/api/search/quick?q=${encodeURIComponent(text)}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`quick search: ${res.status}`);
      const raw = (await res.json()) as QuickResponse;
      const data: QuickResult = {
        products: (raw.products ?? []).map(apiProductToProduct),
        categories: raw.categories ?? [],
      };
      const cache = cacheRef.current;
      cache.delete(k);
      cache.set(k, data);
      while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
      if (abortRef.current === controller) {
        setEntry({ key: k, data });
        // Список опций сменился — прежняя активная позиция указывала бы на другую строку.
        setActiveIndex(-1);
      }
    } catch {
      // Прерванный запрос — не ошибка: его сменил более свежий. Остальное (сеть, 5xx)
      // показываем состоянием панели; «Все результаты» остаётся рабочим выходом.
      if (controller.signal.aborted) return;
      if (abortRef.current === controller) {
        setEntry({ key: k, error: true });
        setActiveIndex(-1);
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        inflightKeyRef.current = null;
      }
    }
  }, []);

  // Подсказки для текста поля: из кэша сразу, иначе — запрос после паузы в наборе.
  const requestSuggestions = useCallback(
    (text: string) => {
      cancelPending();
      const k = normalize(text);
      if (k.length < MIN_QUERY) {
        abortInflight();
        return;
      }
      const cached = cacheRef.current.get(k);
      if (cached) {
        abortInflight();
        setEntry({ key: k, data: cached });
        return;
      }
      if (inflightKeyRef.current === k) return; // этот же текст уже в пути
      debounceRef.current = setTimeout(() => {
        debounceRef.current = null;
        void fetchQuick(text.trim(), k);
      }, DEBOUNCE_MS);
    },
    [abortInflight, cancelPending, fetchQuick],
  );

  const close = useCallback(() => {
    cancelPending();
    setOpen(false);
    setActiveIndex(-1);
  }, [cancelPending]);

  const handleChange = (value: string) => {
    setQuery(value);
    setActiveIndex(-1);
    setOpen(normalize(value).length >= MIN_QUERY);
    requestSuggestions(value);
  };

  const openPanel = () => {
    if (!active) return;
    setOpen(true);
    // Ответа по текущему тексту может не быть: таймер сбросили по Esc или уходу фокуса,
    // или поле пришло заполненным со страницы поиска.
    if (!current || current.error) requestSuggestions(query);
  };

  const navigate = (href: string) => {
    close();
    abortInflight();
    // На телефоне прячем клавиатуру: панель закрыта, дальше — переход.
    inputRef.current?.blur();
    router.push(href);
  };

  const choose = (option: Option) => {
    if (option.kind === "product") setQuery(option.item.cardName || option.item.name);
    navigate(option.href);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    navigate(searchHref(query));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!active) return;
      e.preventDefault();
      if (!expanded) {
        openPanel();
        return;
      }
      const n = options.length;
      if (!n) return;
      setActiveIndex((i) => {
        if (e.key === "ArrowDown") return i < 0 || i >= n - 1 ? 0 : i + 1;
        return i <= 0 ? n - 1 : i - 1;
      });
      return;
    }
    if (e.key === "Enter" && activeOption) {
      e.preventDefault();
      choose(activeOption);
      return;
    }
    if (e.key === "Escape" && expanded) {
      // Chrome по Esc очищает input[type=search] — при открытой панели Esc только
      // закрывает её; следующий Esc (панель уже закрыта) очистит поле как обычно.
      e.preventDefault();
      close();
    }
  };

  // Закрытие по клику/тапу вне компонента.
  useEffect(() => {
    const onPointerDownOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        pointerInsideRef.current = false;
        close();
      }
    };
    document.addEventListener("mousedown", onPointerDownOutside);
    return () => document.removeEventListener("mousedown", onPointerDownOutside);
  }, [close]);

  // Активная опция всегда в видимой части прокручиваемой панели.
  const activeId = activeOption?.id;
  useEffect(() => {
    if (!activeId) return;
    document.getElementById(activeId)?.scrollIntoView?.({ block: "nearest" });
  }, [activeId]);

  // Чистим таймер и текущий запрос при размонтировании.
  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      abortRef.current?.abort();
    },
    [],
  );

  // Одна фраза на ответ: текст меняется только с приходом нового ответа (или сменой
  // запроса), повторный рендер того же ответа диктор не перечитывает.
  let announcement = "";
  if (expanded && failed) announcement = "Не удалось загрузить подсказки";
  else if (expanded && result) {
    const c = result.categories.length;
    const p = result.products.length;
    const sections = `${c} ${pluralize(c, "раздел", "раздела", "разделов")}`;
    const goods = `${p} ${pluralize(p, "товар", "товара", "товаров")}`;
    announcement = empty ? "Ничего не найдено" : `Найдено: ${sections}, ${goods}`;
  }

  const categoryOptions = options.filter((o) => o.kind === "category");
  const productOptions = options.filter((o) => o.kind === "product");
  const allOption = options.find((o) => o.kind === "all");

  return (
    <div
      ref={containerRef}
      className={cn("relative w-full max-w-xl", className)}
      onPointerDown={() => {
        pointerInsideRef.current = true;
      }}
      onClick={() => {
        pointerInsideRef.current = false;
      }}
      onBlur={(e) => {
        // Tab и любой другой уход фокуса за пределы поиска закрывают панель.
        if (pointerInsideRef.current) return;
        if (!containerRef.current?.contains(e.relatedTarget as Node | null)) close();
      }}
    >
      <form onSubmit={handleSubmit} className="relative" role="search">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
          aria-hidden
        />
        <input
          ref={inputRef}
          type="search"
          role="combobox"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onFocus={openPanel}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="h-11 w-full rounded-md border border-line bg-surface py-2 pl-9 pr-8 text-base text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none [&::-webkit-search-cancel-button]:hidden"
          aria-label="Поиск товаров"
          aria-autocomplete="list"
          aria-expanded={expanded}
          aria-controls={listboxId}
          aria-activedescendant={activeId}
          autoComplete="off"
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              close();
              abortInflight();
              inputRef.current?.focus();
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink"
            aria-label="Очистить поиск"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </form>

      {expanded && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[70vh] overflow-auto overscroll-contain rounded-md border border-line bg-raised shadow-lg">
          {loading && <p className="px-3 py-2.5 text-sm text-ink-3">Ищем…</p>}
          {failed && (
            <p className="px-3 py-2.5 text-sm text-ink-3">Не удалось загрузить подсказки</p>
          )}
          {empty && (
            <p className="px-3 py-2.5 text-sm text-ink-3">
              Ничего не найдено по запросу «{query.trim()}»
            </p>
          )}

          <ul id={listboxId} role="listbox" aria-label="Подсказки поиска">
            {categoryOptions.length > 0 && (
              <li role="presentation">
                <ul role="group" aria-labelledby={`${baseId}-cats`}>
                  <li
                    role="presentation"
                    id={`${baseId}-cats`}
                    className="px-3 pb-1 pt-2.5 text-xs font-semibold uppercase tracking-wide text-ink-3"
                  >
                    Разделы
                  </li>
                  {categoryOptions.map((option) => {
                    if (option.kind !== "category") return null;
                    const c = option.item;
                    return (
                      <OptionRow
                        key={option.id}
                        id={option.id}
                        selected={activeId === option.id}
                        onSelect={() => choose(option)}
                        onHover={() => setActiveIndex(options.indexOf(option))}
                        className="flex min-h-11 items-center gap-2.5 px-3 py-2 text-left"
                      >
                        <LayoutGrid className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                        <span className="min-w-0">
                          <span className="block truncate text-[15px] text-ink">{c.name}</span>
                          {c.name !== c.category.name && (
                            <span className="block truncate text-xs text-ink-3">
                              {c.category.name}
                            </span>
                          )}
                        </span>
                      </OptionRow>
                    );
                  })}
                </ul>
              </li>
            )}

            {productOptions.length > 0 && (
              <li
                role="presentation"
                className={cn(categoryOptions.length > 0 && "border-t border-line")}
              >
                <ul role="group" aria-labelledby={`${baseId}-products`}>
                  <li
                    role="presentation"
                    id={`${baseId}-products`}
                    className="px-3 pb-1 pt-2.5 text-xs font-semibold uppercase tracking-wide text-ink-3"
                  >
                    Товары
                  </li>
                  {productOptions.map((option) => {
                    if (option.kind !== "product") return null;
                    const p = option.item;
                    return (
                      <OptionRow
                        key={option.id}
                        id={option.id}
                        selected={activeId === option.id}
                        onSelect={() => choose(option)}
                        onHover={() => setActiveIndex(options.indexOf(option))}
                        className="flex items-center gap-3 px-3 py-2 text-left"
                      >
                        {/* Фото — оформление: название опции диктор берёт из текста. */}
                        <div aria-hidden className="shrink-0">
                          <ProductImage
                            src={p.image}
                            alt=""
                            sizes="52px"
                            normalized={p.imageNormalized}
                            className="h-[52px] w-[52px] [&_img]:p-1 [&_svg]:h-5 [&_svg]:w-5"
                          />
                        </div>
                        <span className="min-w-0 flex-1">
                          <span className="line-clamp-2 text-sm leading-snug text-ink">
                            {p.cardName || p.name}
                          </span>
                          {p.brand && (
                            <span className="mt-0.5 block truncate text-xs text-ink-3">
                              {p.brand}
                            </span>
                          )}
                        </span>
                        <span className="flex shrink-0 flex-col items-end gap-1 text-right">
                          <span className="whitespace-nowrap text-sm font-semibold text-ink">
                            {p.price.final != null
                              ? formatPrice(p.price.final, p.price.currency)
                              : "Цена уточняется"}
                          </span>
                          <ProductAvailability stock={p.stock} />
                        </span>
                      </OptionRow>
                    );
                  })}
                </ul>
              </li>
            )}

            {allOption && (
              <OptionRow
                id={allOption.id}
                selected={activeId === allOption.id}
                onSelect={() => choose(allOption)}
                onHover={() => setActiveIndex(options.indexOf(allOption))}
                className={cn(
                  "flex min-h-11 items-center px-3 py-2 text-left text-[15px] text-accent",
                  (categoryOptions.length > 0 || productOptions.length > 0) &&
                    "border-t border-line",
                )}
              >
                Все результаты по запросу «{query.trim()}»
              </OptionRow>
            )}
          </ul>
        </div>
      )}

      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>
    </div>
  );
}
