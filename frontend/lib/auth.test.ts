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
  checkAuth,
  deleteAccount,
  getMe,
  loginHref,
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
    expect(mockedFetch).toHaveBeenCalledWith("/api/account/logout", { method: "POST" });
  });

  it("login шлёт POST на BFF-путь account/login", async () => {
    mockedFetch.mockResolvedValueOnce({ id: 1 });
    await login("+79001112233", "pass");
    expect(mockedFetch).toHaveBeenCalledWith(
      "/api/account/login",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("getMe возвращает null, когда пользователь не вошёл (401/403)", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError("401", 401));
    expect(await getMe()).toBeNull();
  });

  // Раньше здесь тоже возвращался null — и кабинет выкидывал на форму входа
  // человека с живой сессией, стоило серверу ответить 500 или сети моргнуть.
  it("getMe пробрасывает сбой сервера — это не «пользователь не вошёл»", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError("500", 500));
    await expect(getMe()).rejects.toBeInstanceOf(ApiError);
  });

  it("checkAuth различает гостя и сбой", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError("403", 403));
    expect(await checkAuth()).toBe("anonymous");

    // ApiError со статусом 0 — так apiFetch сообщает про обрыв связи.
    mockedFetch.mockRejectedValueOnce(new ApiError("нет связи", 0));
    expect(await checkAuth()).toBe("error");

    mockedFetch.mockRejectedValueOnce(new ApiError("лимит", 429));
    expect(await checkAuth()).toBe("error");

    const user = { id: 1, phone: "+79001112233" };
    mockedFetch.mockResolvedValueOnce(user);
    expect(await checkAuth()).toEqual(user);
  });

  it("loginHref запоминает, куда человек шёл", () => {
    expect(loginHref("/account/invoices")).toBe("/account/login?next=%2Faccount%2Finvoices");
    expect(loginHref()).toBe("/account/login");
    // Чужой абсолютный адрес в next не пропускаем — это открытый редирект.
    expect(loginHref("https://evil.example/phish")).toBe("/account/login");
  });

  // #574: сбой возвращает "error", а не [] — иначе экран заказов показывал
  // «Заказов пока нет» и выдавал ошибку сервера за пустой список.
  it("getOrders возвращает \"error\" при ApiError", async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError("403", 403));
    expect(await getOrders()).toBe("error");
  });

  // Страница ответа — 24 заказа, кнопки «показать ещё» в кабинете нет: без
  // дозагрузки всё, что старше двух десятков заказов, пропадало из виду.
  it("getOrders дочитывает все страницы", async () => {
    const page = (from: number, n: number) =>
      Array.from({ length: n }, (_, i) => ({ order_number: `П-${from + i}` }));
    mockedFetch
      .mockResolvedValueOnce({ count: 130, results: page(0, 100) })
      .mockResolvedValueOnce({ count: 130, results: page(100, 30) });

    const orders = await getOrders();

    expect(Array.isArray(orders) && orders.length).toBe(130);
    expect(mockedFetch).toHaveBeenNthCalledWith(1, "/api/orders?limit=100&offset=0", {
      method: "GET",
    });
    expect(mockedFetch).toHaveBeenNthCalledWith(2, "/api/orders?limit=100&offset=100", {
      method: "GET",
    });
  });

  it("getOrders не делает лишнего запроса, когда всё поместилось", async () => {
    mockedFetch.mockResolvedValueOnce({ count: 2, results: [{ id: 1 }, { id: 2 }] });

    expect(await getOrders()).toHaveLength(2);
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it("updateMe отправляет PATCH профиля через BFF", async () => {
    const updated = { id: 1, full_name: "Иван", email: "ivan@example.com" };
    mockedFetch.mockResolvedValueOnce(updated);

    await expect(updateMe({ full_name: "Иван", email: "ivan@example.com" })).resolves.toBe(
      updated,
    );
    expect(mockedFetch).toHaveBeenCalledWith("/api/account/me", {
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

    expect(mockedFetch).toHaveBeenNthCalledWith(1, "/api/account/change-phone", {
      method: "POST",
      body: JSON.stringify({ new_phone: "+79001112233", password: "secret" }),
    });
    expect(mockedFetch).toHaveBeenNthCalledWith(2, "/api/account/delete", {
      method: "POST",
    });
  });
});
