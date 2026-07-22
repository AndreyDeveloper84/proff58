import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// #574: сводка заказа и честные состояния справочников доставки.
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

const cartState = {
  cart: {
    lines: [{ id: 1, name: "Перфоратор", quantity: 1, line_total: "1000.00" }],
    currency: "RUB",
  } as Record<string, unknown>,
  loading: false,
  total: 1000,
  refresh: vi.fn(),
};
vi.mock("@/components/cart/CartProvider", () => ({ useCart: () => cartState }));
vi.mock("@/components/cart/PromoCodeField", () => ({ PromoCodeField: () => null }));
vi.mock("@/lib/orders", () => ({ placeOrder: vi.fn() }));
vi.mock("@/lib/order-storage", () => ({ stashOrder: vi.fn() }));
vi.mock("@/lib/delivery", () => ({ getDeliveryZones: vi.fn(), getDeliverySlots: vi.fn() }));

import { getDeliverySlots, getDeliveryZones } from "@/lib/delivery";
import CheckoutPage from "./page";

const mockedGetZones = getDeliveryZones as unknown as ReturnType<typeof vi.fn>;
const mockedGetSlots = getDeliverySlots as unknown as ReturnType<typeof vi.fn>;

const ZONES = [
  { zone: "penza", name: "Пенза (курьер)", type: "courier", cost: "500.00", free_delivery: false },
];

describe("CheckoutPage — сводка заказа (#574)", () => {
  beforeEach(() => {
    pushMock.mockReset();
    mockedGetZones.mockReset();
    mockedGetZones.mockResolvedValue(ZONES);
    mockedGetSlots.mockReset();
    mockedGetSlots.mockResolvedValue([]);
  });

  it("итог назван предварительным — сумму считает сервер", async () => {
    render(<CheckoutPage />);
    expect(await screen.findByText("Предварительный итог:")).toBeTruthy();
    expect(screen.queryByText("Итого:")).toBeNull();
    expect(
      screen.getByText(/Окончательную сумму, включая доставку, считает сервер/),
    ).toBeTruthy();
  });

  it("строка доставки видна до выбора зоны", async () => {
    render(<CheckoutPage />);
    expect(await screen.findByText("Доставка:")).toBeTruthy();
    expect(screen.getByText("рассчитается после выбора зоны")).toBeTruthy();
  });

  it("предупреждение о резерве показано без числа минут", async () => {
    render(<CheckoutPage />);
    const notice = await screen.findByText(/товар зарезервируем за вами до оплаты/i);
    expect(notice.textContent).not.toMatch(/\d+\s*минут/);
  });

  it("пока слоты не загружены, «интервалов нет» не показывается", async () => {
    // Ответ не приходит — состояние загрузки должно держаться.
    mockedGetSlots.mockReturnValue(new Promise(() => {}));
    render(<CheckoutPage />);
    expect(await screen.findByText(/Загружаем свободные интервалы/)).toBeTruthy();
    expect(screen.queryByText(/Доступных интервалов доставки нет/)).toBeNull();
  });

  it("сбой загрузки слотов отличается от пустого справочника", async () => {
    mockedGetSlots.mockResolvedValue("error");
    render(<CheckoutPage />);
    expect(await screen.findByText(/Не удалось загрузить интервалы доставки/)).toBeTruthy();
    expect(screen.queryByText(/Доступных интервалов доставки нет/)).toBeNull();
  });

  it("сбой загрузки зон объясняется пользователю", async () => {
    mockedGetZones.mockResolvedValue("error");
    render(<CheckoutPage />);
    await waitFor(() =>
      expect(screen.getByText(/Не удалось загрузить зоны доставки/)).toBeTruthy(),
    );
  });
});
