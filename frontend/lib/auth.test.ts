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
import { getMe, getOrders, login, logout } from "./auth";

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

  it("getOrders возвращает [] при ApiError", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError("403", 403));
    expect(await getOrders()).toEqual([]);
  });
});
