import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Header по утверждённому макету: каталог, поиск, корзина и сравнение работают,
// инфо-страницы остаются без мёртвых ссылок.
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({ count: 3 }),
}));
// SearchBar тянет suggest через fetch — подменяем на заглушку.
vi.mock("./SearchBar", () => ({
  SearchBar: () => <div data-testid="searchbar" />,
}));

import { AuthStateProvider } from "@/components/auth/AuthStateProvider";
import type { AuthState } from "@/lib/auth-state";
import { Header } from "./Header";
import { COMPARE_STORAGE_KEY } from "@/lib/compare";
import { SITE } from "@/lib/site";

// Состояние входа приходит из серверного расчёта (app/layout.tsx) — в тестах
// подставляем его напрямую, как это делает провайдер.
function renderHeader(state: AuthState = "anonymous") {
  return render(
    <AuthStateProvider state={state}>
      <Header />
    </AuthStateProvider>,
  );
}

describe("Header (#586)", () => {
  beforeEach(() => {
    document.documentElement.classList.remove("dark");
    // Список сравнения живёт в localStorage: без очистки счётчик протекал бы
    // из предыдущего теста.
    localStorage.clear();
  });

  it("каталог, корзина и избранное — рабочие ссылки", () => {
    renderHeader("authenticated");
    const catalog = screen.getAllByRole("link", { name: new RegExp(SITE.header.catalogLabel) })[0];
    expect(catalog).toHaveAttribute("href", "/catalog");
    expect(screen.getAllByRole("link", { name: /Избранное/ })[0]).toHaveAttribute(
      "href",
      "/wishlist",
    );
    // Корзина показывает актуальный счётчик из useCart.
    const cart = screen.getAllByRole("link", { name: /Корзина, товаров: 3/ })[0];
    expect(cart).toHaveAttribute("href", "/cart");
    expect(within(cart).getByText("3")).toBeInTheDocument();
  });

  // Раньше здесь стояла серая нерабочая плашка «Скоро»: страницы сравнения не
  // существовало. Теперь это обычная ссылка со счётчиком выбранного.
  it("«Сравнение» — рабочая ссылка со счётчиком выбранного", () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["bosch", "makita"]));
    renderHeader();

    const compare = screen.getByRole("link", { name: /Сравнение, товаров: 2/ });
    expect(compare).toHaveAttribute("href", "/compare");
    expect(within(compare).getByText("2")).toBeInTheDocument();
  });

  it("пустое сравнение — ссылка без счётчика", () => {
    renderHeader();

    const compare = screen.getByRole("link", { name: "Сравнение" });
    expect(compare).toHaveAttribute("href", "/compare");
    expect(within(compare).queryByText("0")).toBeNull();
  });

  // #592: инфо-страниц (/service, /delivery, …) не существует — пункты topbar
  // рендерятся future-текстом, а не битыми ссылками.
  it("инфо-пункты topbar — не ссылки, пока страниц нет", () => {
    renderHeader();
    for (const l of SITE.header.topLinks) {
      const el = screen.getByText(l.label);
      expect(el.closest("a")).toBeNull();
    }
  });

  // Переключатель темы переехал в topbar, к часам работы: в основной строке он
  // стоял среди корзины/избранного и читался как действие с товаром.
  it("переключатель темы стоит в topbar справа от часов работы", () => {
    renderHeader();
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
    renderHeader();
    const inHeaderRow = screen
      .getAllByRole("button", { name: /тему/i })
      .find((b) => b.parentElement?.className.includes("lg:hidden"));

    expect(inHeaderRow).toBeDefined();
    expect(inHeaderRow!.className).toContain("sm:grid");
  });

  // На телефоне (<640px) логотип и две иконки занимают строку целиком — третья
  // вызывала бы горизонтальную прокрутку, поэтому там переключатель в меню.
  it("на телефоне переключатель темы остаётся в бургер-меню", () => {
    renderHeader();
    fireEvent.click(screen.getByRole("button", { name: "Меню" }));

    const inMenu = within(screen.getByRole("navigation")).getByRole("button", { name: /тему/i });
    expect(inMenu.parentElement!.className).toContain("sm:hidden");
  });

  it("телефон и график из макета отображаются", () => {
    renderHeader();
    expect(screen.getAllByText(SITE.phone.display)[0]).toBeInTheDocument();
    expect(screen.getByText(SITE.phoneNote)).toBeInTheDocument();
    // График встречается дважды: topbar и подменю «Контакты».
    expect(screen.getAllByText(SITE.schedule)[0]).toBeInTheDocument();
  });

  it("инфо-пункты topbar содержат hover-подменю с контентом сервисной полосы", () => {
    renderHeader();
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

  // Гостю «Кабинет» ведёт прямо на вход. Пока он вёл в кабинет, серверный гвард
  // разворачивал человека уже после смены адреса: в строке успевал мелькнуть
  // /account/profile, а на месте сайта — пустая страница.
  it("гостю кабинет ведёт на форму входа с возвратом, избранное — на витрину", () => {
    renderHeader();

    expect(screen.getAllByRole("link", { name: /Личный кабинет/ })[0]).toHaveAttribute(
      "href",
      "/account/login?next=%2Faccount%2Fprofile",
    );
    // Избранное переехало на витрину и доступно без аккаунта — гостя туда и ведём.
    expect(screen.getAllByRole("link", { name: /Избранное/ })[0]).toHaveAttribute(
      "href",
      "/wishlist",
    );
  });

  it("вошедшего ведут прямо в кабинет", () => {
    renderHeader("authenticated");

    expect(screen.getAllByRole("link", { name: /Личный кабинет/ })[0]).toHaveAttribute(
      "href",
      "/account/profile",
    );
  });

  // Сессия есть, маркера входа нет (человек вошёл до того, как маркер появился).
  // Раньше такому показывали форму входа, хотя он был залогинен, — и всё
  // чинилось перезагрузкой. Ведём по назначению: доступ проверит гвард кабинета.
  it("«может быть вошёл» ведёт в кабинет, а не на форму входа", () => {
    renderHeader("unknown");

    expect(screen.getAllByRole("link", { name: /Личный кабинет/ })[0]).toHaveAttribute(
      "href",
      "/account/profile",
    );
    expect(screen.getAllByRole("link", { name: /Избранное/ })[0]).toHaveAttribute(
      "href",
      "/wishlist",
    );
  });
});
