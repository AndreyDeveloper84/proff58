import { fireEvent, render, screen, within } from "@testing-library/react";
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

  // Переключатель темы переехал в topbar, к часам работы: в основной строке он
  // стоял среди корзины/избранного и читался как действие с товаром.
  it("переключатель темы стоит в topbar справа от часов работы", () => {
    render(<Header />);
    const toggle = screen.getAllByRole("button", { name: /тёмную тему/i })[0];
    const row = toggle.parentElement!;
    const schedule = within(row).getByText(SITE.schedule);

    const nodes = Array.from(row.children);
    expect(nodes.indexOf(schedule.closest("span")!)).toBeLessThan(nodes.indexOf(toggle));
    // Именно topbar (h-8), а не основная строка шапки (h-14).
    expect(row.parentElement!.className).toContain("h-8");
  });

  // Основная строка шапки видна всегда, бургер-меню — нет. Переключатель, до
  // которого надо сначала открыть меню, пользователь считает несуществующим,
  // поэтому на планшетах и узких десктопных окнах он стоит в ряду иконок.
  it("на узких ширинах переключатель темы стоит в шапке, а не только в меню", () => {
    render(<Header />);
    const inHeaderRow = screen
      .getAllByRole("button", { name: /тему/i })
      .find((b) => b.parentElement?.className.includes("lg:hidden"));

    expect(inHeaderRow).toBeDefined();
    expect(inHeaderRow!.className).toContain("sm:grid");
  });

  // На телефоне (<640px) логотип и две иконки занимают строку целиком — третья
  // вызывала бы горизонтальную прокрутку, поэтому там переключатель в меню.
  it("на телефоне переключатель темы остаётся в бургер-меню", () => {
    render(<Header />);
    fireEvent.click(screen.getByRole("button", { name: "Меню" }));

    const inMenu = within(screen.getByRole("navigation")).getByRole("button", { name: /тему/i });
    expect(inMenu.parentElement!.className).toContain("sm:hidden");
  });

  it("телефон и график из макета отображаются", () => {
    render(<Header />);
    expect(screen.getAllByText(SITE.phone.display)[0]).toBeInTheDocument();
    expect(screen.getByText(SITE.phoneNote)).toBeInTheDocument();
    // График встречается дважды: topbar и подменю «Контакты».
    expect(screen.getAllByText(SITE.schedule)[0]).toBeInTheDocument();
  });

  it("инфо-пункты topbar содержат hover-подменю с контентом сервисной полосы", () => {
    render(<Header />);
    // Подменю всегда в DOM (показ — CSS hover/focus-within): контент проверяем напрямую.
    for (const link of SITE.header.topLinks) {
      expect(screen.getByText(link.label)).toBeInTheDocument();
      for (const m of link.menu) {
        expect(screen.getByText(m.title)).toBeInTheDocument();
      }
    }
    // «Контакты» рендерятся из storefront: адрес и e-mail присутствуют.
    expect(screen.getAllByText(/Онежский проезд/)[0]).toBeInTheDocument();
    expect(screen.getByText(SITE.email)).toBeInTheDocument();
  });
});
