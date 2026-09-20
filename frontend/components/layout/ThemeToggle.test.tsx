import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { THEME_INIT_SCRIPT, THEME_STORAGE_KEY, ThemeToggle } from "./ThemeToggle";

afterEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.classList.remove("dark");
});

describe("ThemeToggle", () => {
  it("в светлой теме предлагает тёмную (луна), в тёмной — светлую (солнце)", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Включить тёмную тему" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByRole("button", { name: "Включить светлую тему" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("переключение ставит тему на <html> и запоминает выбор", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button"));

    // Обе формы: data-theme — для токенов globals.css, .dark — для утилит `dark:`.
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    fireEvent.click(screen.getByRole("button"));

    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("инициализация до гидрации: сохранённая тёмная тема переживает перезагрузку", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    // Скрипт из <head> исполняем как обычный код — он не должен зависеть от React.
    new Function(THEME_INIT_SCRIPT)();

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");

    render(<ThemeToggle />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  // UX-01: тема ОС не влияет на сайт — ни при первом входе, ни при смене на лету.
  function withDarkSystem(run: (fire: () => void) => void) {
    const original = window.matchMedia;
    const handlers: ((e: { matches: boolean }) => void)[] = [];
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: () => ({
        matches: true,
        addEventListener: (_: string, h: (e: { matches: boolean }) => void) => handlers.push(h),
        removeEventListener() {},
      }),
    });
    try {
      run(() => handlers.forEach((h) => h({ matches: true })));
    } finally {
      Object.defineProperty(window, "matchMedia", { writable: true, value: original });
    }
  }

  it("без сохранённого выбора сайт светлый даже при тёмной теме ОС", () => {
    withDarkSystem(() => {
      new Function(THEME_INIT_SCRIPT)();
      expect(document.documentElement).toHaveAttribute("data-theme", "light");
      expect(document.documentElement).not.toHaveClass("dark");
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    });
  });

  it("смена темы ОС на лету сайт не перекрашивает", () => {
    withDarkSystem((fireSystemChange) => {
      new Function(THEME_INIT_SCRIPT)();
      render(<ThemeToggle />);
      act(() => fireSystemChange());
      expect(document.documentElement).toHaveAttribute("data-theme", "light");
      expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "false");
    });
  });

  it("мусор в хранилище трактуется как отсутствие выбора — светлая", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "auto");
    new Function(THEME_INIT_SCRIPT)();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("недоступный localStorage: сайт светлый, переключатель работает", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    try {
      // Стартуем с «чужой» темой на <html>: скрипт обязан поставить светлую сам.
      document.documentElement.setAttribute("data-theme", "dark");
      new Function(THEME_INIT_SCRIPT)();
      expect(document.documentElement).toHaveAttribute("data-theme", "light");

      render(<ThemeToggle />);
      fireEvent.click(screen.getByRole("button"));
      expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    } finally {
      getItem.mockRestore();
      setItem.mockRestore();
    }
  });

  it("выбор темы в соседней вкладке применяется и здесь", () => {
    render(<ThemeToggle />);
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: THEME_STORAGE_KEY }));
    });
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });
});
