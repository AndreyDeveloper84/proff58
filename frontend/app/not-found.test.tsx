import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import NotFound from "./not-found";

// Раньше здесь была стандартная заглушка Next.js — «404 This page could not be
// found» по-английски и без единой ссылки. Проверяем ровно то, ради чего её
// заменили: страница на русском и из неё есть куда пойти.
describe("Страница 404", () => {
  it("объясняет по-русски и даёт выходы", () => {
    render(<NotFound />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Такой страницы нет");
    expect(screen.getByRole("link", { name: "Каталог товаров" })).toHaveAttribute(
      "href",
      "/catalog",
    );
    expect(screen.getByRole("link", { name: "На главную" })).toHaveAttribute("href", "/");
  });

  // Форма, а не клиентский компонент: страница ошибки должна работать и тогда,
  // когда со скриптами что-то не так.
  it("поиск работает обычной формой методом GET", () => {
    const { container } = render(<NotFound />);

    const form = container.querySelector("form")!;
    expect(form).toHaveAttribute("action", "/search");
    expect(form).toHaveAttribute("method", "get");
    expect(form.querySelector('input[name="q"]')).toBeInTheDocument();
  });
});
