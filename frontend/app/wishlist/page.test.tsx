import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/account/wishlist",
}));

const toggleMock = vi.fn();
let wishlistState = { ids: new Set<number>(), loaded: true, isGuest: false };

vi.mock("@/components/wishlist/WishlistProvider", () => ({
  useWishlist: () => ({
    ids: wishlistState.ids,
    loaded: wishlistState.loaded,
    has: (id: number) => wishlistState.ids.has(id),
    toggle: toggleMock,
    isPending: () => false,
    isGuest: wishlistState.isGuest,
    limitReached: false,
  }),
}));

vi.mock("@/lib/wishlist-products", () => ({ fetchWishlistProducts: vi.fn() }));

// Карточка тянет корзину — здесь проверяется избранное, а не «в корзину».
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({ count: 0, addItem: vi.fn(), lines: [] }),
}));

import { AuthStateProvider } from "@/components/auth/AuthStateProvider";
import type { AuthState } from "@/lib/auth-state";
import { fetchWishlistProducts } from "@/lib/wishlist-products";
import WishlistPage from "./page";

function renderAs(state: AuthState) {
  return render(
    <AuthStateProvider state={state}>
      <WishlistPage />
    </AuthStateProvider>,
  );
}

const mockedFetch = fetchWishlistProducts as unknown as ReturnType<typeof vi.fn>;

function product(id: number, name: string) {
  return {
    id,
    slug: `p-${id}`,
    name,
    cardName: name,
    brand: "Bosch",
    price: { final: 1000, currency: "RUB" as const },
    stock: "in" as const,
    stockQty: 5,
    specs: [],
    badges: [],
  };
}

describe("WishlistPage", () => {
  beforeEach(() => {
    toggleMock.mockReset();
    mockedFetch.mockReset();
    wishlistState = { ids: new Set<number>(), loaded: true, isGuest: false };
  });

  it("показывает карточки сохранённых товаров", async () => {
    wishlistState = { ids: new Set([7]), loaded: true, isGuest: false };
    mockedFetch.mockResolvedValue([product(7, "Дрель аккумуляторная")]);

    render(<WishlistPage />);

    expect(await screen.findByText("Дрель аккумуляторная")).toBeInTheDocument();
    expect(mockedFetch).toHaveBeenCalledWith([7]);
  });

  it("пустое избранное — предложение перейти в каталог", async () => {
    render(<WishlistPage />);

    expect(await screen.findByText("В избранном пока пусто")).toBeInTheDocument();
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it("сбой загрузки карточек не выдаём за пустое избранное", async () => {
    wishlistState = { ids: new Set([7]), loaded: true, isGuest: false };
    mockedFetch.mockRejectedValue(new Error("нет связи"));

    render(<WishlistPage />);

    expect(await screen.findByText("Не удалось загрузить избранное")).toBeInTheDocument();
    expect(screen.queryByText("В избранном пока пусто")).not.toBeInTheDocument();
  });

  it("товар, снятый из избранного, исчезает со страницы сразу", async () => {
    wishlistState = { ids: new Set([7, 8]), loaded: true, isGuest: false };
    mockedFetch.mockResolvedValue([product(7, "Дрель"), product(8, "Перфоратор")]);

    const view = render(<WishlistPage />);
    await screen.findByText("Дрель");

    // Провайдер убрал id — карточка обязана уйти, не дожидаясь новой загрузки.
    wishlistState = { ids: new Set([8]), loaded: true, isGuest: false };
    view.rerender(<WishlistPage />);

    expect(screen.queryByText("Дрель")).not.toBeInTheDocument();
    expect(screen.getByText("Перфоратор")).toBeInTheDocument();
  });

  it("гостю объясняем, что список живёт в этом браузере", async () => {
    wishlistState = { ids: new Set([7]), loaded: true, isGuest: true };
    mockedFetch.mockResolvedValue([product(7, "Дрель")]);

    render(<WishlistPage />);

    expect(await screen.findByText(/Избранное хранится в этом браузере/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Войдите" })).toHaveAttribute(
      "href",
      "/account/login?next=%2Fwishlist",
    );
  });

  it("вошедшему про браузер не рассказываем", async () => {
    wishlistState = { ids: new Set([7]), loaded: true, isGuest: false };
    mockedFetch.mockResolvedValue([product(7, "Дрель")]);

    render(<WishlistPage />);

    await screen.findByText("Дрель");
    expect(screen.queryByText(/хранится в этом браузере/)).not.toBeInTheDocument();
  });

  // «Избранное» есть в меню кабинета, но страница живёт на витрине — переход по
  // пункту меню выбрасывал вошедшего наружу, и это читалось как «кабинет закрылся».
  it("вошедшему страница открывается внутри кабинета", async () => {
    renderAs("authenticated");

    expect(await screen.findByText("В избранном пока пусто")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Разделы личного кабинета" })).toBeInTheDocument();
  });

  it("гостю кабинет не показываем — обычная страница витрины", async () => {
    renderAs("anonymous");

    expect(await screen.findByText("В избранном пока пусто")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Разделы личного кабинета" })).toBeNull();
    expect(screen.getByRole("navigation", { name: "Хлебные крошки" })).toBeInTheDocument();
  });
});
