"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";

// Переключатель светлой/тёмной темы. Тема живёт на <html> сразу в двух формах:
// data-theme (семантические токены globals.css) и класс .dark (@custom-variant
// dark для утилит `dark:`) — компоненты вправе пользоваться любой.
//
// Дефолт — системный (prefers-color-scheme); явный выбор пользователя
// сохраняется в localStorage и системную настройку перебивает. Чтобы тема не
// мигала на загрузке, начальное состояние ставит THEME_INIT_SCRIPT в <head> ДО
// гидрации — приём из next/docs «preventing flash before hydration».

export const THEME_STORAGE_KEY = "theme";

// Порядок важен: сохранённый выбор > системная тема. Скрипт исполняется при
// разборе HTML, поэтому первый кадр рисуется уже в правильной теме.
export const THEME_INIT_SCRIPT = `(function(){try{var s=localStorage.getItem('${THEME_STORAGE_KEY}');var t=(s==='dark'||s==='light')?s:(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');var e=document.documentElement;e.setAttribute('data-theme',t);e.classList.toggle('dark',t==='dark');}catch(e){}})();`;

// Тема — внешнее состояние (атрибут на <html>), а не React-стейт: её ставит
// инлайн-скрипт до React. useSyncExternalStore читает факт из DOM, поэтому
// компонент не может разойтись с реальным оформлением страницы.
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(callback: () => void) {
  listeners.add(callback);
  // storage — смена темы в соседней вкладке; matchMedia — смена темы в ОС
  // (учитываем, только пока пользователь не выбрал тему руками).
  window.addEventListener("storage", callback);
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  const onSystemChange = (event: MediaQueryListEvent) => {
    if (storedTheme() != null) return;
    applyTheme(event.matches ? "dark" : "light");
    emit();
  };
  media?.addEventListener("change", onSystemChange);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", callback);
    media?.removeEventListener("change", onSystemChange);
  };
}

function storedTheme(): "light" | "dark" | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "dark" || value === "light" ? value : null;
  } catch {
    return null; // приватный режим/отключённый storage
  }
}

function applyTheme(theme: "light" | "dark") {
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  root.classList.toggle("dark", theme === "dark");
}

function isDark() {
  return document.documentElement.getAttribute("data-theme") === "dark";
}

function setDark(next: boolean) {
  applyTheme(next ? "dark" : "light");
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next ? "dark" : "light");
  } catch {
    /* тема просто не запомнится между визитами */
  }
  emit();
}

export function ThemeToggle({ className }: { className?: string }) {
  const dark = useSyncExternalStore(
    subscribe,
    isDark,
    () => false, // серверный снимок — детерминированно светлая
  );

  return (
    <button
      type="button"
      onClick={() => setDark(!dark)}
      aria-label={dark ? "Включить светлую тему" : "Включить тёмную тему"}
      aria-pressed={dark}
      title={dark ? "Светлая тема" : "Тёмная тема"}
      className={cn(
        "grid h-10 w-10 shrink-0 place-items-center rounded-md text-header-ink transition hover:bg-header-ink/10",
        className,
      )}
    >
      {dark ? (
        <Sun className="h-[18px] w-[18px]" aria-hidden />
      ) : (
        <Moon className="h-[18px] w-[18px]" aria-hidden />
      )}
    </button>
  );
}
