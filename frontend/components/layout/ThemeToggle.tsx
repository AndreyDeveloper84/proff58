"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";

// #586: переключатель светлой/тёмной темы. Тема = класс `.dark` на <html>
// (тот же механизм, что @custom-variant dark и [data-theme] в globals.css).
// Дефолт — светлая (утверждённый макет). Выбор хранится в localStorage; чтобы
// не мигало при загрузке, начальное состояние ставит инлайн-скрипт в layout
// ДО гидрации (см. THEME_INIT_SCRIPT).
export const THEME_STORAGE_KEY = "theme";

export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('${THEME_STORAGE_KEY}');if(t==='dark'){document.documentElement.classList.add('dark');}}catch(e){}})();`;

// Тема — внешнее состояние (класс на <html>). Читаем через useSyncExternalStore:
// SSR-снимок всегда светлый (детерминированно, без hydration mismatch), клиентский —
// фактический класс. Подписка ловит и наш toggle, и смену темы в другой вкладке.
const listeners = new Set<() => void>();

function subscribe(callback: () => void) {
  listeners.add(callback);
  window.addEventListener("storage", callback);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", callback);
  };
}

function isDark() {
  return document.documentElement.classList.contains("dark");
}

function setDarkMode(next: boolean) {
  document.documentElement.classList.toggle("dark", next);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next ? "dark" : "light");
  } catch {
    /* приватный режим/отключённый storage — тема просто не запомнится */
  }
  listeners.forEach((l) => l());
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const dark = useSyncExternalStore(
    subscribe,
    isDark,
    () => false, // серверный снимок — всегда светлая тема
  );

  return (
    <button
      type="button"
      onClick={() => setDarkMode(!dark)}
      aria-label={dark ? "Включить светлую тему" : "Включить тёмную тему"}
      aria-pressed={dark}
      className={`grid h-9 w-9 place-items-center rounded-md text-header-ink transition hover:bg-header-ink/10 ${className}`}
    >
      {dark ? (
        <Sun className="h-[18px] w-[18px]" aria-hidden />
      ) : (
        <Moon className="h-[18px] w-[18px]" aria-hidden />
      )}
    </button>
  );
}
