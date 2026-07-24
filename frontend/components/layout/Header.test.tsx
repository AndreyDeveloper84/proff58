import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Header по утверждённому макету — каталог/поиск/корзина работают,
// сравнение остаётся без мёртвой ссылки.
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({ count: 3 }),
}));
// SearchBar тянет suggest через fetch — подменяем на заглушку.
vi.mock("./SearchBar", () => ({
  SearchBar: () => <div data-testid="searchbar" />,
}));

import { Header } from "./Header";
import { SITE } from "@/lib/site";

describe("Header (#586)", () => {
  beforeEach(() => {
    document.documentElement.classList.remove("dark");
  });

  it("каталог, корзина и избранное — рабочие ссылки", () => {
    render(<Header />);
    const catalog = screen.getAllByRole("link", { name: new RegExp(SITE.header.catalogLabel) })[0];
    expect(catalog).toHaveAttribute("href", "/catalog");
    expect(screen.getAllByRole("link", { name: /Избранное/ })[0]).toHaveAttribute(
      "href",
      "/account/wishlist",
    );
    // Корзина показывает актуальный счётчик из useCart.
    const cart = screen.getAllByRole("link", { name: /Корзина, товаров: 3/ })[0];
    expect(cart).toHaveAttribute("href", "/cart");
    expect(within(cart).getByText("3")).toBeInTheDocument();
  });

  it("«Сравнение» показано, но без ссылки (Wave 2, страницы нет)", () => {
    render(<Header />);
    const compare = screen.getByText("Сравнение");
    // Не ссылка и не ведёт в никуда — просто future-плашка.
    expect(compare.closest("a")).toBeNull();
    expect(screen.queryByRole("link", { name: /Сравнение/ })).toBeNull();
  });

  // #592: инфо-страниц (/service, /delivery, …) не существует — пункты topbar
  // рендерятся future-текстом, а не битыми ссылками.
  it("инфо-пункты topbar — не ссылки, пока страниц нет", () => {
    render(<Header />);
    for (const l of SITE.header.topLinks) {
      const el = screen.getByText(l.label);
      expect(el.closest("a")).toBeNull();
    }
  });

  it("не добавляет отсутствующий в утверждённом макете переключатель темы", () => {
    render(<Header />);
    expect(screen.queryByRole("button", { name: /тёмную тему/i })).toBeNull();
  });

  it("телефон и график из макета отображаются", () => {
    render(<Header />);
    expect(screen.getAllByText(SITE.phone.display)[0]).toBeInTheDocument();
    expect(screen.getByText(SITE.phoneNote)).toBeInTheDocument();
    expect(screen.getByText(SITE.schedule)).toBeInTheDocument();
  });
});
