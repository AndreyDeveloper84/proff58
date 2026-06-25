"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, X } from "lucide-react";

// Подсказки из ProductSuggestView (#52) через same-origin BFF: GET /api/search/suggest?q=
// → [{id,name,slug}]. Браузер ходит только в Next route handler, тот проксирует в Django.
type Suggestion = { id: number; name: string; slug: string };

const MIN_QUERY = 2;

export function SearchBar() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Прерываем устаревший запрос подсказок, чтобы поздний ответ не «перебил» свежий.
  const abortRef = useRef<AbortController | null>(null);

  const fetchSuggestions = useCallback(async (q: string) => {
    abortRef.current?.abort();
    if (q.length < MIN_QUERY) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const res = await fetch(`/api/search/suggest?q=${encodeURIComponent(q)}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!res.ok) return;
      const data = (await res.json()) as Suggestion[];
      setSuggestions(data);
      setOpen(true);
    } catch {
      // AbortError или сбой сети — подсказки некритичны, молча игнорируем.
    } finally {
      // Снимаем индикатор только для актуального запроса (не для прерванного).
      if (abortRef.current === controller) setLoading(false);
    }
  }, []);

  const handleChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(value), 250);
  };

  const goToSearch = (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setOpen(false);
    router.push(`/search?q=${encodeURIComponent(trimmed)}`);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    goToSearch(query);
  };

  const handleSuggestionClick = (s: Suggestion) => {
    setOpen(false);
    setQuery(s.name);
    router.push(`/product/${s.slug}`);
  };

  // Закрытие по клику вне компонента.
  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  // Чистим таймер и текущий запрос при размонтировании.
  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      abortRef.current?.abort();
    },
    [],
  );

  return (
    <div ref={containerRef} className="relative w-full max-w-xl">
      <form onSubmit={handleSubmit} className="relative" role="search">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3"
          aria-hidden
        />
        <input
          ref={inputRef}
          type="search"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onFocus={() => {
            if (suggestions.length > 0) setOpen(true);
          }}
          placeholder="Поиск товаров…"
          className="w-full rounded-md border border-line bg-canvas py-2 pl-9 pr-8 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none"
          aria-label="Поиск товаров"
          autoComplete="off"
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setSuggestions([]);
              setOpen(false);
              abortRef.current?.abort();
              inputRef.current?.focus();
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink"
            aria-label="Очистить поиск"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </form>

      {open && suggestions.length > 0 && (
        <ul className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-md border border-line bg-raised shadow-lg">
          {suggestions.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => handleSuggestionClick(s)}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm text-ink hover:bg-surface"
              >
                <Search className="h-3.5 w-3.5 shrink-0 text-ink-3" aria-hidden />
                <span className="truncate">{s.name}</span>
              </button>
            </li>
          ))}
          <li className="border-t border-line">
            <button
              type="button"
              onClick={() => goToSearch(query)}
              className="w-full px-3 py-2 text-left text-sm text-accent hover:bg-surface"
            >
              Показать все результаты
            </button>
          </li>
        </ul>
      )}

      {open && loading && suggestions.length === 0 && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-md border border-line bg-raised p-3 text-center text-sm text-ink-3 shadow-lg">
          Поиск…
        </div>
      )}
    </div>
  );
}
