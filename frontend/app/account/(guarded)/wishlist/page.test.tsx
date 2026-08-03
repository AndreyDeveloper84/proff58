import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/account/wishlist",
}));

const toggleMock = vi.fn();
let wishlistState = { ids: new Set<number>(), loaded: true };

vi.mock("@/components/wishlist/WishlistProvider", () => ({
  useWishlist: () => ({
    ids: wishlistState.ids,
    loaded: wishlistState.loaded,
    has: (id: number) => wishlistState.ids.has(id),
    toggle: toggleMock,
    pendingId: null,
  }),
}));

vi.mock("@/lib/wishlist-products", () => ({ fetchWishlistProducts: vi.fn() }));

// Карточка тянет корзину — здесь проверяется избранное, а не «в корзину».
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({ count: 0, addItem: vi.fn(), lines: [] }),
}));

import { fetchWishlistProducts } from "@/lib/wishlist-products";
import WishlistPage from "./page";

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
    wishlistState = { ids: new Set<number>(), loaded: true };
  });

  it("показывает карточки сохранённых товаров", async () => {
    wishlistState = { ids: new Set([7]), loaded: true };
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
    wishlistState = { ids: new Set([7]), loaded: true };
    mockedFetch.mockRejectedValue(new Error("нет связи"));

    render(<WishlistPage />);

    expect(await screen.findByText("Не удалось загрузить избранное")).toBeInTheDocument();
    expect(screen.queryByText("В избранном пока пусто")).not.toBeInTheDocument();
  });

  it("товар, снятый из избранного, исчезает со страницы сразу", async () => {
    wishlistState = { ids: new Set([7, 8]), loaded: true };
    mockedFetch.mockResolvedValue([product(7, "Дрель"), product(8, "Перфоратор")]);

    const view = render(<WishlistPage />);
    await screen.findByText("Дрель");

    // Провайдер убрал id — карточка обязана уйти, не дожидаясь новой загрузки.
    wishlistState = { ids: new Set([8]), loaded: true };
    view.rerender(<WishlistPage />);

    expect(screen.queryByText("Дрель")).not.toBeInTheDocument();
    expect(screen.getByText("Перфоратор")).toBeInTheDocument();
  });
});
