import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const replaceMock = vi.fn();
const routerMock = { push: pushMock, replace: replaceMock };

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/account/wishlist",
}));
vi.mock("@/lib/auth", () => ({
  checkAuth: vi.fn(),
  loginHref: (next?: string) => (next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login"),
  getWishlist: vi.fn(),
  removeWishlistItem: vi.fn(),
}));

import { checkAuth, getWishlist, removeWishlistItem } from "@/lib/auth";
import WishlistPage from "./page";

const mockedGetMe = checkAuth as unknown as ReturnType<typeof vi.fn>;
const mockedGetWishlist = getWishlist as unknown as ReturnType<typeof vi.fn>;
const mockedRemove = removeWishlistItem as unknown as ReturnType<typeof vi.fn>;

describe("WishlistPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetWishlist.mockReset();
    mockedRemove.mockReset();
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedGetWishlist.mockResolvedValue([
      {
        product_id: 7,
        product_name: "Дрель аккумуляторная",
        product_slug: "drel-akkumulyatornaya",
      },
    ]);
  });

  it("удаляет товар отдельной кнопкой и показывает пустое состояние", async () => {
    mockedRemove.mockResolvedValue(undefined);
    render(<WishlistPage />);

    await screen.findByText("Дрель аккумуляторная");
    fireEvent.click(
      screen.getByRole("button", {
        name: "Удалить «Дрель аккумуляторная» из избранного",
      }),
    );

    await waitFor(() => expect(mockedRemove).toHaveBeenCalledWith(7));
    expect(await screen.findByText("В избранном пока пусто")).toBeInTheDocument();
  });

  it("возвращает карточку при ошибке удаления", async () => {
    mockedRemove.mockRejectedValue(new Error("Сервис недоступен."));
    render(<WishlistPage />);

    await screen.findByText("Дрель аккумуляторная");
    fireEvent.click(
      screen.getByRole("button", {
        name: "Удалить «Дрель аккумуляторная» из избранного",
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Сервис недоступен.");
    expect(screen.getByText("Дрель аккумуляторная")).toBeInTheDocument();
  });
});
