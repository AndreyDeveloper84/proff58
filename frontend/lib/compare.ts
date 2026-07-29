"use client";

import { useCallback, useSyncExternalStore } from "react";

import { COMPARE_LIMIT } from "@/lib/constants";

// Список сравнения живёт в localStorage, а не на сервере: выбор «посмотрю эти
// три перфоратора рядом» — сиюминутный, и требовать ради него регистрацию
// незачем (в отличие от избранного, которое человек копит месяцами).
//
// Храним только slug'и: цены и остатки меняются, и подтягивать их надо свежими
// при каждом открытии страницы, а не показывать снимок недельной давности.

export const COMPARE_STORAGE_KEY = "compare";

// Реэкспорт: страница и кнопка берут лимит отсюда, а серверный route-handler —
// из lib/constants (импортировать в него клиентский модуль нельзя).
export { COMPARE_LIMIT };

const listeners = new Set<() => void>();

// useSyncExternalStore сравнивает снимки через Object.is: если возвращать новый
// массив на каждый вызов, React уйдёт в бесконечный ререндер. Поэтому держим
// разобранное значение в кэше и обновляем только при реальном изменении.
let cache: string[] = [];
let cacheRaw: string | null = null;

const EMPTY: string[] = [];

function read(): string[] {
  try {
    const raw = localStorage.getItem(COMPARE_STORAGE_KEY);
    if (raw === cacheRaw) return cache;
    cacheRaw = raw;
    const parsed = raw ? JSON.parse(raw) : [];
    cache = Array.isArray(parsed) ? parsed.filter((s) => typeof s === "string") : [];
    return cache;
  } catch {
    // Приватный режим, отключённый storage или испорченный JSON — сравнение
    // просто не работает, но витрина не падает.
    cacheRaw = null;
    cache = EMPTY;
    return cache;
  }
}

function write(slugs: string[]): void {
  try {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(slugs));
  } catch {
    /* выбор не сохранится между визитами — не повод ломать клик */
  }
  cacheRaw = null; // следующий read() перечитает и обновит кэш
  listeners.forEach((listener) => listener());
}

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  // storage — тот же сайт в соседней вкладке: добавили товар там, счётчик
  // в шапке должен обновиться и здесь.
  const onStorage = (event: StorageEvent) => {
    if (event.key === COMPARE_STORAGE_KEY || event.key === null) {
      cacheRaw = null;
      callback();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", onStorage);
  };
}

/** Добавить/убрать товар. Возвращает false, если упёрлись в лимит. */
export function toggleCompare(slug: string): boolean {
  const current = read();
  if (current.includes(slug)) {
    write(current.filter((s) => s !== slug));
    return true;
  }
  if (current.length >= COMPARE_LIMIT) return false;
  write([...current, slug]);
  return true;
}

export function removeFromCompare(slug: string): void {
  write(read().filter((s) => s !== slug));
}

export function clearCompare(): void {
  write([]);
}

/**
 * Текущий список сравнения.
 *
 * На сервере — всегда пустой: localStorage там нет, а отрендерить счётчик «3» и
 * тут же схлопнуть его до нуля хуже, чем показать ноль сразу.
 */
export function useCompare() {
  const slugs = useSyncExternalStore(subscribe, read, () => EMPTY);
  const has = useCallback((slug: string) => slugs.includes(slug), [slugs]);
  return {
    slugs,
    count: slugs.length,
    has,
    isFull: slugs.length >= COMPARE_LIMIT,
    toggle: toggleCompare,
    remove: removeFromCompare,
    clear: clearCompare,
  };
}
