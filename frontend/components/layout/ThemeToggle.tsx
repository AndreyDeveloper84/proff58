"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";

// Переключатель светлой/тёмной темы. Тема живёт на <html> сразу в двух формах:
// data-theme (семантические токены globals.css) и класс .dark (@custom-variant
// dark для утилит `dark:`) — компоненты вправе пользоваться любой.
//
// Дефолт — светлая (UX-01): сохранённый выбор пользователя → иначе светлая.
// Тема ОС на сайт не влияет — ни при первом входе, ни при её смене на лету:
// покупатель с тёмной системой видел тёмный магазин, которого не выбирал.
// Чтобы тема не мигала на загрузке, начальное состояние ставит
// THEME_INIT_SCRIPT в <head> ДО гидрации — приём из next/docs «preventing
// flash before hydration».

export const THEME_STORAGE_KEY = "theme";

// Порядок: сохранённый выбор → светлая. Чтение localStorage обёрнуто отдельно:
// при запрещённом/сломанном хранилище тема всё равно ставится (светлая), а не
// остаётся «какой получится». Скрипт исполняется при разборе HTML, поэтому
// первый кадр рисуется уже в правильной теме.
export const THEME_INIT_SCRIPT = `(function(){var t='light';try{var s=localStorage.getItem('${THEME_STORAGE_KEY}');if(s==='dark'||s==='light')t=s;}catch(e){}var r=document.documentElement;r.setAttribute('data-theme',t);r.classList.toggle('dark',t==='dark');})();`;

// Тема — внешнее состояние (атрибут на <html>), а не React-стейт: её ставит
// инлайн-скрипт до React. useSyncExternalStore читает факт из DOM, поэтому
// компонент не может разойтись с реальным оформлением страницы.
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(callback: () => void) {
  listeners.add(callback);
  // storage — смена темы в соседней вкладке. Снимок читается из DOM, поэтому
  // сначала переносим выбор на <html> этой вкладки, потом будим подписчика:
  // без applyTheme событие приходило, а страница оставалась в старой теме.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== THEME_STORAGE_KEY) return;
    applyTheme(storedTheme() ?? "light");
    callback();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", onStorage);
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
