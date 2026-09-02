import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Header по утверждённому макету: каталог, поиск, корзина и сравнение работают,
// инфо-страницы остаются без мёртвых ссылок.
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({ count: 3 }),
}));
// Избранное — как и корзина: состояние задаём напрямую, без провайдера и похода
// на сервер (наполнение списка проверяет WishlistProvider.test).
const wishlist = vi.hoisted(() => ({ ids: new Set<number>() }));
vi.mock("@/components/wishlist/WishlistProvider", () => ({
  useWishlist: () => ({ ids: wishlist.ids }),
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
function renderHeader(
  state: AuthState = "anonymous",
  props: Partial<ComponentProps<typeof Header>> = {},
) {
  return render(
    <AuthStateProvider state={state}>
      <Header {...props} />
    </AuthStateProvider>,
  );
}

describe("Header (#586)", () => {
  beforeEach(() => {
    document.documentElement.classList.remove("dark");
    // Список сравнения живёт в localStorage: без очистки счётчик протекал бы
    // из предыдущего теста.
    localStorage.clear();
    wishlist.ids = new Set();
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

  // Сердечко на карточке — единственное подтверждение клика, и на длинной
  // выдаче его не видно. Счётчик в шапке показывает выбор целиком, как у
  // сравнения и корзины.
  it("«Избранное» показывает счётчик выбранного", () => {
    wishlist.ids = new Set([11, 22]);
    renderHeader();

    const link = screen.getByRole("link", { name: "Избранное, товаров: 2" });
    expect(link).toHaveAttribute("href", "/wishlist");
    expect(within(link).getByText("2")).toBeInTheDocument();
  });

  it("пустое избранное — ссылка без счётчика", () => {
    renderHeader();

    const link = screen.getByRole("link", { name: "Избранное" });
    expect(within(link).queryByText("0")).toBeNull();
  });

  // На телефоне ряда иконок нет вовсе — там избранное живёт в бургер-меню, и
  // без счётчика клик по сердечку остался бы вообще без подтверждения.
  it("счётчик виден и в мобильном меню", () => {
    wishlist.ids = new Set([11, 22, 33]);
    renderHeader();
    fireEvent.click(screen.getByRole("button", { name: "Меню" }));

    const inMenu = within(screen.getByRole("navigation")).getByRole("link", {
      name: "Избранное, товаров: 3",
    });
    expect(within(inMenu).getByText("3")).toBeInTheDocument();
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

describe("Инфо-пункты служебной полосы (DRF-1442)", () => {
  it("ведут на страницу, когда она опубликована", () => {
    renderHeader("anonymous", { infoPages: [{ slug: "warranty", title: "Гарантийный ремонт" }] });

    expect(screen.getByRole("link", { name: "Гарантии" })).toHaveAttribute(
      "href",
      "/info/warranty",
    );
  });

  it("остаются подсказкой, пока страница не опубликована", () => {
    // Страницы ведутся в админке и заводятся черновиками: ссылка на черновик
    // дала бы 404 из шапки — то есть на каждой странице сайта.
    renderHeader("anonymous", { infoPages: [] });

    expect(screen.queryByRole("link", { name: "Гарантии" })).toBeNull();
    expect(screen.getByText("Гарантии")).toBeInTheDocument();
  });

  it("подсказка показывается в обоих случаях", () => {
    renderHeader("anonymous", { infoPages: [] });

    expect(screen.getByText("Официальная гарантия")).toBeInTheDocument();
  });

  it("пункт подменю ведёт на свою страницу отдельно от ярлыка", () => {
    renderHeader("anonymous", { infoPages: [{ slug: "payment", title: "Оплата" }] });

    // «Доставка и оплата» ведёт на доставку (её страницы нет — значит не ссылка),
    // а пункт «Оплата» внутри подсказки — на оплату.
    expect(screen.getByRole("link", { name: "Оплата" })).toHaveAttribute("href", "/info/payment");
    expect(screen.queryByRole("link", { name: "Доставка и оплата" })).toBeNull();
  });
});
