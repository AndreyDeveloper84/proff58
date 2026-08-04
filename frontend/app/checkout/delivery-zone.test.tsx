import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({
    cart: { lines: [{ id: 1, name: "Перфоратор", quantity: 1, line_total: "1000.00" }] },
    loading: false,
    total: 1000,
    refresh: vi.fn(),
  }),
}));

vi.mock("@/lib/orders", () => ({ placeOrder: vi.fn() }));
vi.mock("@/lib/order-storage", () => ({ stashOrder: vi.fn() }));
// #569: страница импортирует и getDeliverySlots — без него мок роняет рендер.
vi.mock("@/lib/delivery", () => ({ getDeliveryZones: vi.fn(), getDeliverySlots: vi.fn() }));

import { getDeliverySlots, getDeliveryZones } from "@/lib/delivery";
import { placeOrder } from "@/lib/orders";
import CheckoutPage from "./page";

const mockedPlaceOrder = placeOrder as unknown as ReturnType<typeof vi.fn>;
const mockedGetZones = getDeliveryZones as unknown as ReturnType<typeof vi.fn>;
const mockedGetSlots = getDeliverySlots as unknown as ReturnType<typeof vi.fn>;

const ZONES = [
  { zone: "penza", name: "Пенза (город)", type: "courier", cost: "500.00", free_delivery: false },
  { zone: "oblast-cdek", name: "Область (СДЭК)", type: "courier", cost: "0.00", free_delivery: false },
  { zone: "pickup-main", name: "Самовывоз со склада", type: "pickup", cost: "0.00", free_delivery: true },
];

function fillBaseFields() {
  fireEvent.change(screen.getByLabelText(/^Имя/), { target: { value: "Иван" } });
  fireEvent.change(screen.getByLabelText(/^Телефон/), { target: { value: "+79001112233" } });
  // Адрес — по частям (см. lib/delivery-address): улица и дом обязательны.
  fireEvent.change(screen.getByLabelText(/^Улица/), { target: { value: "Ленина" } });
  fireEvent.change(screen.getByLabelText(/^Дом/), { target: { value: "1" } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: /оформить/i }));
}

describe("CheckoutPage — зона доставки (аудит №5)", () => {
  beforeEach(() => {
    pushMock.mockReset();
    mockedPlaceOrder.mockReset();
    mockedPlaceOrder.mockResolvedValue({ order_number: "П-1" });
    mockedGetZones.mockReset();
    mockedGetZones.mockResolvedValue(ZONES);
    // Слоты в этих тестах не участвуют — пустой справочник (пикер скрыт).
    mockedGetSlots.mockReset();
    mockedGetSlots.mockResolvedValue([]);
  });

  it("курьер: зона обязательна — без неё заказ не отправляется", async () => {
    render(<CheckoutPage />);
    await screen.findByLabelText(/^Зона доставки/); // дождаться загрузки зон
    fillBaseFields();
    submit();

    expect(await screen.findByText(/Выберите зону доставки/)).toBeTruthy();
    expect(mockedPlaceOrder).not.toHaveBeenCalled();
  });

  it("курьер: выбранная зона уходит в delivery_zone", async () => {
    render(<CheckoutPage />);
    const select = await screen.findByLabelText(/^Зона доставки/);
    fillBaseFields();
    fireEvent.change(select, { target: { value: "penza" } });
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({
      delivery_method: "courier",
      delivery_zone: "penza",
    });
    // pickup-зона не предлагается в селекте курьерки.
    expect(screen.queryByRole("option", { name: /Самовывоз со склада/ })).toBeNull();
  });

  it("самовывоз: зона не требуется и уходит пустой", async () => {
    render(<CheckoutPage />);
    await screen.findByLabelText(/^Зона доставки/);
    fireEvent.change(screen.getByLabelText(/^Имя/), { target: { value: "Иван" } });
    fireEvent.change(screen.getByLabelText(/^Телефон/), { target: { value: "+79001112233" } });
    fireEvent.click(screen.getByLabelText("Самовывоз"));
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({
      delivery_method: "pickup",
      delivery_zone: "",
    });
  });

  it("справочник зон недоступен: заказ создаётся без зоны (как раньше)", async () => {
    mockedGetZones.mockResolvedValue([]);
    render(<CheckoutPage />);
    fillBaseFields();
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({ delivery_zone: "" });
  });
});
