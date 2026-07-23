import { beforeEach, describe, expect, it, vi } from "vitest";

// Мокаем единый API-клиент — проверяем, что auth ходит через него (BFF + CSRF),
// а не сырым fetch напрямую в Django.
vi.mock("@/lib/api", async () => {
  class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  }
  return { ApiError, apiFetch: vi.fn() };
});

import { ApiError, apiFetch } from "@/lib/api";
import {
  changePhone,
  deleteAccount,
  getMe,
  getOrder,
  getOrders,
  login,
  logout,
  removeWishlistItem,
  updateMe,
} from "./auth";

const mockedFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

describe("auth client (M-11)", () => {
  beforeEach(() => mockedFetch.mockReset());

  it("logout идёт POST через BFF (CSRF-aware) и ожидается", async () => {
    mockedFetch.mockResolvedValueOnce(undefined);
    await logout();
    expect(mockedFetch).toHaveBeenCalledWith("/api/account/logout/", { method: "POST" });
  });

  it("login шлёт POST на BFF-путь account/login", async () => {
    mockedFetch.mockResolvedValueOnce({ id: 1 });
    await login("+79001112233", "pass");
    expect(mockedFetch).toHaveBeenCalledWith(
      "/api/account/login/",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("getMe возвращает null при ApiError (не пробрасывает)", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError("401", 401));
    expect(await getMe()).toBeNull();
  });

  // #574: сбой возвращает "error", а не [] — иначе экран заказов показывал
  // «Заказов пока нет» и выдавал ошибку сервера за пустой список.
  it("getOrders возвращает \"error\" при ApiError", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError("403", 403));
    expect(await getOrders()).toBe("error");
  });

  it("updateMe отправляет PATCH профиля через BFF", async () => {
    const updated = { id: 1, full_name: "Иван", email: "ivan@example.com" };
    mockedFetch.mockResolvedValueOnce(updated);

    await expect(updateMe({ full_name: "Иван", email: "ivan@example.com" })).resolves.toBe(
      updated,
    );
    expect(mockedFetch).toHaveBeenCalledWith("/api/account/me/", {
      method: "PATCH",
      body: JSON.stringify({ full_name: "Иван", email: "ivan@example.com" }),
    });
  });

  it("удаляет товар из избранного отдельным DELETE-запросом", async () => {
    mockedFetch.mockResolvedValueOnce({ ok: true });
    await removeWishlistItem(42);
    expect(mockedFetch).toHaveBeenCalledWith("/api/account/wishlist", {
      method: "DELETE",
      body: JSON.stringify({ product_id: 42 }),
    });
  });

  it("запрашивает конкретный заказ по безопасно закодированному номеру", async () => {
    mockedFetch.mockResolvedValueOnce({ id: 7 });
    await getOrder("П-2026/7");
    expect(mockedFetch).toHaveBeenCalledWith(
      `/api/orders/${encodeURIComponent("П-2026/7")}`,
      { method: "GET" },
    );
  });

  it("чувствительные действия идут POST-запросами", async () => {
    mockedFetch.mockResolvedValue(undefined);
    await changePhone("+79001112233", "secret");
    await deleteAccount();

    expect(mockedFetch).toHaveBeenNthCalledWith(1, "/api/account/change-phone/", {
      method: "POST",
      body: JSON.stringify({ new_phone: "+79001112233", password: "secret" }),
    });
    expect(mockedFetch).toHaveBeenNthCalledWith(2, "/api/account/delete/", {
      method: "POST",
    });
  });
});
