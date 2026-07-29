import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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

  it("инициализация до гидрации: сохранённый выбор важнее системной темы", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    // Скрипт из <head> исполняем как обычный код — он не должен зависеть от React.
    new Function(THEME_INIT_SCRIPT)();

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");

    render(<ThemeToggle />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  it("без сохранённого выбора берёт системную тему", () => {
    const original = window.matchMedia;
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: () => ({ matches: true, addEventListener() {}, removeEventListener() {} }),
    });

    new Function(THEME_INIT_SCRIPT)();
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull(); // системная — не выбор

    Object.defineProperty(window, "matchMedia", { writable: true, value: original });
  });
});
