import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// #574: список заказов показывает резерв и путь к отзыву, а сбой загрузки
// не выдаётся за «заказов пока нет».
const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  usePathname: () => "/account/orders",
}));
vi.mock("@/lib/auth", () => ({
  checkAuth: vi.fn(), getOrders: vi.fn(),
  loginHref: (next?: string) => (next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login"),
}));

import { checkAuth, getOrders } from "@/lib/auth";
import OrdersPage from "./page";

const mockedGetMe = checkAuth as unknown as ReturnType<typeof vi.fn>;
const mockedGetOrders = getOrders as unknown as ReturnType<typeof vi.fn>;

const HOUR_AHEAD = new Date(Date.now() + 3_600_000).toISOString();
const HOUR_AGO = new Date(Date.now() - 3_600_000).toISOString();

function order(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    order_number: "П-1",
    display_status: "Новый",
    customer_type: "b2c",
    payment_status: "pending",
    fulfillment_status: "new",
    sync_1c_status: "pending",
    delivery_address: "",
    total: "1000.00",
    currency: "RUB",
    created_at: "2026-07-21T10:00:00+03:00",
    items: [],
    ...overrides,
  };
}

describe("OrdersPage (#574)", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetOrders.mockReset();
    mockedGetMe.mockResolvedValue({ id: 1, customer_type: "b2c" });
  });

  it("активный резерв виден прямо в списке", async () => {
    mockedGetOrders.mockResolvedValue([
      order({ reservation_status: "held", reserved_until: HOUR_AHEAD }),
    ]);
    render(<OrdersPage />);
    expect(await screen.findByText(/Товар зарезервирован до/)).toBeTruthy();
  });

  it("истёкший резерв объясняет, что дальше", async () => {
    mockedGetOrders.mockResolvedValue([
      order({ reservation_status: "held", reserved_until: HOUR_AGO, reservation_expired: true }),
    ]);
    render(<OrdersPage />);
    expect(await screen.findByText(/Время резерва истекло/)).toBeTruthy();
  });

  it("у доставленного заказа есть путь к отзыву", async () => {
    mockedGetOrders.mockResolvedValue([
      order({ fulfillment_status: "completed", payment_status: "paid" }),
    ]);
    render(<OrdersPage />);
    const link = await screen.findByRole("link", { name: /Оставить отзыв/ });
    expect(link.getAttribute("href")).toBe("/account/orders/%D0%9F-1#review");
  });

  it("#573 B2B: у доставленного заказа юрлица пути к отзыву нет", async () => {
    mockedGetOrders.mockResolvedValue([
      order({ fulfillment_status: "completed", payment_status: "paid", customer_type: "b2b" }),
    ]);
    render(<OrdersPage />);
    // «Открыть заказ» есть — значит карточка отрисовалась; «Оставить отзыв» — нет.
    await screen.findByRole("link", { name: /Открыть заказ/ });
    expect(screen.queryByRole("link", { name: /Оставить отзыв/ })).toBeNull();
  });

  it("сбой загрузки не выдаётся за пустой список", async () => {
    mockedGetOrders.mockResolvedValue("error");
    render(<OrdersPage />);
    expect(await screen.findByText("Не удалось загрузить заказы")).toBeTruthy();
    expect(screen.queryByText("Заказов пока нет")).toBeNull();
  });

  it("пустой список остаётся пустым состоянием", async () => {
    mockedGetOrders.mockResolvedValue([]);
    render(<OrdersPage />);
    expect(await screen.findByText("Заказов пока нет")).toBeTruthy();
  });
});
