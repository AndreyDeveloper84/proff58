import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({
  getWishlist: vi.fn(),
  addWishlistItem: vi.fn(),
  addWishlistItems: vi.fn(),
  removeWishlistItem: vi.fn(),
}));

import { AuthStateProvider } from "@/components/auth/AuthStateProvider";
import { ApiError } from "@/lib/api";
import { addWishlistItem, addWishlistItems, getWishlist, removeWishlistItem } from "@/lib/auth";
import type { AuthState } from "@/lib/auth-state";
import { WISHLIST_STORAGE_KEY } from "@/lib/wishlist-storage";
import { useWishlist, WishlistProvider } from "./WishlistProvider";

const mockedGet = getWishlist as unknown as ReturnType<typeof vi.fn>;
const mockedAdd = addWishlistItem as unknown as ReturnType<typeof vi.fn>;
const mockedAddMany = addWishlistItems as unknown as ReturnType<typeof vi.fn>;
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

const stored = () => JSON.parse(localStorage.getItem(WISHLIST_STORAGE_KEY) ?? "[]");

describe("WishlistProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    mockedGet.mockReset();
    mockedAdd.mockReset();
    mockedAddMany.mockReset();
    mockedRemove.mockReset();
    mockedGet.mockResolvedValue([]);
    mockedAddMany.mockResolvedValue(undefined);
  });

  // --- Гость: избранное работает без аккаунта, как список сравнения ---

  it("гостю сохраняет товар в браузере и не ходит на сервер", async () => {
    renderProbe("anonymous");
    await screen.findByText("готово:нет");

    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("готово:в избранном")).toBeInTheDocument();
    expect(stored()).toEqual([7]);
    expect(mockedAdd).not.toHaveBeenCalled();
    expect(mockedGet).not.toHaveBeenCalled();
  });

  it("повторный клик гостя снимает товар", async () => {
    localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify([7]));
    renderProbe("anonymous");
    await screen.findByText("готово:в избранном");

    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("готово:нет")).toBeInTheDocument();
    expect(stored()).toEqual([]);
  });

  // --- Вход: список гостя переезжает в аккаунт ---

  it("при входе переносит накопленное в аккаунт и чистит браузер", async () => {
    localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify([7, 9]));
    mockedGet.mockResolvedValue([
      { product_id: 7, product_name: "Дрель", product_slug: "drel" },
      { product_id: 9, product_name: "Пила", product_slug: "pila" },
    ]);

    renderProbe("authenticated");

    await waitFor(() => expect(mockedAddMany).toHaveBeenCalledWith([7, 9]));
    expect(await screen.findByText("готово:в избранном")).toBeInTheDocument();
    await waitFor(() => expect(stored()).toEqual([]));
  });

  it("неудачный перенос не стирает список из браузера", async () => {
    localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify([7]));
    mockedAddMany.mockRejectedValue(new Error("нет связи"));

    renderProbe("authenticated");

    await waitFor(() => expect(mockedAddMany).toHaveBeenCalled());
    await waitFor(() => expect(mockedGet).toHaveBeenCalled());
    expect(stored()).toEqual([7]);
  });

  it("без накопленного переносить нечего", async () => {
    renderProbe("authenticated");

    await waitFor(() => expect(mockedGet).toHaveBeenCalled());
    expect(mockedAddMany).not.toHaveBeenCalled();
  });

  // --- Вошедший: сервер ---

  it("вошедшему сохраняет товар на сервере и показывает это сразу", async () => {
    mockedAdd.mockResolvedValue(undefined);
    renderProbe("authenticated");
    await screen.findByText("готово:нет");

    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("готово:в избранном")).toBeInTheDocument();
    await waitFor(() => expect(mockedAdd).toHaveBeenCalledWith(7));
  });

  it("уже сохранённый товар снимается", async () => {
    mockedGet.mockResolvedValue([{ product_id: 7, product_name: "Дрель", product_slug: "drel" }]);
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

  // Симптом с production: cookie в браузере есть, а сессии за ней нет. Интерфейс
  // считал такого человека вошедшим, каждый клик уходил на сервер, получал 401 и
  // откатывался — сердечко не реагировало вообще.
  it("протухшая сессия: клик виден сразу и сохраняется в браузере", async () => {
    mockedAdd.mockRejectedValue(new ApiError("Сессия истекла.", 403));
    renderProbe("unknown");
    await screen.findByText("готово:нет");

    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("готово:в избранном")).toBeInTheDocument();
    await waitFor(() => expect(stored()).toEqual([7]));
  });

  it("отказ на загрузке списка тоже переводит в гостевой режим", async () => {
    mockedGet.mockResolvedValue("unauthorized");
    renderProbe("unknown");
    await waitFor(() => expect(mockedGet).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("готово:в избранном")).toBeInTheDocument();
    expect(mockedAdd).not.toHaveBeenCalled();  // на сервер больше не ходим
    await waitFor(() => expect(stored()).toEqual([7]));
  });

  it("сбой загрузки списка не выдаётся за пустое избранное", async () => {
    mockedGet.mockResolvedValue("error");
    renderProbe("authenticated");

    expect(await screen.findByText("грузим:нет")).toBeInTheDocument();
  });
});
