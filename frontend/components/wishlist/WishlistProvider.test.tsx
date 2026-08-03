import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
  usePathname: () => "/catalog/perforatory",
}));

vi.mock("@/lib/auth", () => ({
  getWishlist: vi.fn(),
  addWishlistItem: vi.fn(),
  removeWishlistItem: vi.fn(),
  loginHref: (next?: string) =>
    next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login",
}));

import { AuthStateProvider } from "@/components/auth/AuthStateProvider";
import { ApiError } from "@/lib/api";
import { addWishlistItem, getWishlist, removeWishlistItem } from "@/lib/auth";
import type { AuthState } from "@/lib/auth-state";
import { useWishlist, WishlistProvider } from "./WishlistProvider";

const mockedGet = getWishlist as unknown as ReturnType<typeof vi.fn>;
const mockedAdd = addWishlistItem as unknown as ReturnType<typeof vi.fn>;
const mockedRemove = removeWishlistItem as unknown as ReturnType<typeof vi.fn>;

function Probe({ productId }: { productId: number }) {
  const { has, toggle, loaded } = useWishlist();
  return (
    <button type="button" onClick={() => toggle(productId)}>
      {loaded ? "готово" : "грузим"}:{has(productId) ? "в избранном" : "нет"}
    </button>
  );
}

function renderProbe(state: AuthState, productId = 7) {
  return render(
    <AuthStateProvider state={state}>
      <WishlistProvider>
        <Probe productId={productId} />
      </WishlistProvider>
    </AuthStateProvider>,
  );
}

describe("WishlistProvider", () => {
  beforeEach(() => {
    pushMock.mockReset();
    mockedGet.mockReset();
    mockedAdd.mockReset();
    mockedRemove.mockReset();
    mockedGet.mockResolvedValue([]);
  });

  it("гостя уводит на вход с возвратом на текущую страницу и не трогает API", async () => {
    renderProbe("anonymous");
    await screen.findByText("готово:нет");

    fireEvent.click(screen.getByRole("button"));

    expect(pushMock).toHaveBeenCalledWith(
      "/account/login?next=%2Fcatalog%2Fperforatory",
    );
    expect(mockedAdd).not.toHaveBeenCalled();
    expect(mockedGet).not.toHaveBeenCalled();
  });

  it("вошедшему сохраняет товар и показывает это сразу", async () => {
    mockedAdd.mockResolvedValue(undefined);
    renderProbe("authenticated");
    await screen.findByText("готово:нет");

    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("готово:в избранном")).toBeInTheDocument();
    await waitFor(() => expect(mockedAdd).toHaveBeenCalledWith(7));
  });

  it("уже сохранённый товар снимается", async () => {
    mockedGet.mockResolvedValue([
      { product_id: 7, product_name: "Дрель", product_slug: "drel" },
    ]);
    mockedRemove.mockResolvedValue(undefined);
    renderProbe("authenticated");
    await screen.findByText("готово:в избранном");

    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("готово:нет")).toBeInTheDocument();
    await waitFor(() => expect(mockedRemove).toHaveBeenCalledWith(7));
  });

  it("отказ сервера откатывает сердечко", async () => {
    mockedAdd.mockRejectedValue(new Error("нет связи"));
    renderProbe("authenticated");
    await screen.findByText("готово:нет");

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => expect(mockedAdd).toHaveBeenCalled());
    expect(await screen.findByText("готово:нет")).toBeInTheDocument();
  });

  it("истёкшая сессия уводит на вход, а не молча теряет клик", async () => {
    mockedAdd.mockRejectedValue(new ApiError("Сессия истекла.", 403));
    renderProbe("unknown");
    await screen.findByText("готово:нет");

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/account/login?next=%2Fcatalog%2Fperforatory"),
    );
  });

  it("клик до прихода списка не затирается ответом сервера", async () => {
    let deliverList: (items: unknown) => void = () => {};
    mockedGet.mockReturnValue(
      new Promise((resolve) => {
        deliverList = resolve;
      }),
    );
    mockedAdd.mockResolvedValue(undefined);
    renderProbe("authenticated");
    await screen.findByText("грузим:нет");

    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(mockedAdd).toHaveBeenCalledWith(7));

    // Список сервер собрал раньше клика — этого товара в нём нет.
    deliverList([{ product_id: 9, product_name: "Другой", product_slug: "drugoy" }]);

    expect(await screen.findByText("готово:в избранном")).toBeInTheDocument();
  });

  it("сбой загрузки списка не выдаётся за пустое избранное", async () => {
    mockedGet.mockResolvedValue("error");
    renderProbe("authenticated");

    expect(await screen.findByText("грузим:нет")).toBeInTheDocument();
  });
});
