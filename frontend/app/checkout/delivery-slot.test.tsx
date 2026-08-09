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
vi.mock("@/lib/delivery", () => ({ getDeliveryZones: vi.fn(), getDeliverySlots: vi.fn() }));

import { ApiError } from "@/lib/api";
import { getDeliverySlots, getDeliveryZones } from "@/lib/delivery";
import { placeOrder } from "@/lib/orders";
import CheckoutPage from "./page";

const mockedPlaceOrder = placeOrder as unknown as ReturnType<typeof vi.fn>;
const mockedGetZones = getDeliveryZones as unknown as ReturnType<typeof vi.fn>;
const mockedGetSlots = getDeliverySlots as unknown as ReturnType<typeof vi.fn>;

const ZONES = [
  { zone: "penza", name: "Пенза (город)", type: "courier", cost: "500.00", free_delivery: false },
];

const SLOTS = [
  { id: 11, date: "2099-07-21", starts_at: "10:00", ends_at: "14:00" },
  { id: 12, date: "2099-07-21", starts_at: "14:00", ends_at: "18:00" },
  { id: 13, date: "2099-07-22", starts_at: "10:00", ends_at: "14:00" },
];

function fillBaseFields() {
  fireEvent.change(screen.getByLabelText(/^Имя/), { target: { value: "Иван" } });
  fireEvent.change(screen.getByLabelText(/^Телефон/), { target: { value: "+79001112233" } });
  // Адрес — по частям (см. lib/delivery-address): улица и дом обязательны.
  fireEvent.change(screen.getByLabelText(/^Улица/), { target: { value: "Ленина" } });
  fireEvent.change(screen.getByLabelText(/^Дом/), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText(/^Куда доставить/), { target: { value: "penza" } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: /оформить/i }));
}

describe("CheckoutPage — слот доставки (#569)", () => {
  beforeEach(() => {
    pushMock.mockReset();
    mockedPlaceOrder.mockReset();
    mockedPlaceOrder.mockResolvedValue({ order_number: "П-1" });
    mockedGetZones.mockReset();
    mockedGetZones.mockResolvedValue(ZONES);
    mockedGetSlots.mockReset();
    mockedGetSlots.mockResolvedValue(SLOTS);
  });

  it("слоты есть: выбор обязателен — без него заказ не отправляется", async () => {
    render(<CheckoutPage />);
    await screen.findByLabelText(/^Дата и время доставки/);
    fillBaseFields();
    submit();

    expect(await screen.findByText(/Выберите дату и время доставки/)).toBeTruthy();
    expect(mockedPlaceOrder).not.toHaveBeenCalled();
  });

  it("выбранный слот уходит в delivery_slot_id", async () => {
    render(<CheckoutPage />);
    const select = await screen.findByLabelText(/^Дата и время доставки/);
    fillBaseFields();
    fireEvent.change(select, { target: { value: "12" } });
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({
      delivery_method: "courier",
      delivery_zone: "penza",
      delivery_slot_id: 12,
    });
  });

  it("самовывоз: пикер скрыт, delivery_slot_id уходит null", async () => {
    render(<CheckoutPage />);
    await screen.findByLabelText(/^Дата и время доставки/);
    fireEvent.change(screen.getByLabelText(/^Имя/), { target: { value: "Иван" } });
    fireEvent.change(screen.getByLabelText(/^Телефон/), { target: { value: "+79001112233" } });
    fireEvent.click(screen.getByRole("radio", { name: /Самовывоз/ }));

    await waitFor(() =>
      expect(screen.queryByLabelText(/^Дата и время доставки/)).toBeNull(),
    );
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({
      delivery_method: "pickup",
      delivery_slot_id: null,
    });
  });

  it("B2B: блок доставки и пикер слота не рендерятся", async () => {
    render(<CheckoutPage />);
    await screen.findByLabelText(/^Дата и время доставки/);
    fireEvent.click(screen.getByLabelText("Организация"));

    await waitFor(() =>
      expect(screen.queryByLabelText(/^Дата и время доставки/)).toBeNull(),
    );
    expect(screen.getByText(/Для юридических лиц — самовывоз/)).toBeTruthy();
  });

  it("слотов нет: подсказка вместо пикера, заказ уходит без слота", async () => {
    mockedGetSlots.mockResolvedValue([]);
    render(<CheckoutPage />);
    await screen.findByLabelText(/^Куда доставить/);
    expect(
      await screen.findByText(/Доступных интервалов доставки нет/),
    ).toBeTruthy();
    fillBaseFields();
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({ delivery_slot_id: null });
  });

  it("смена курьер→самовывоз→курьер сбрасывает выбранный слот", async () => {
    render(<CheckoutPage />);
    const select = await screen.findByLabelText(/^Дата и время доставки/);
    fillBaseFields();
    fireEvent.change(select, { target: { value: "11" } });
    fireEvent.click(screen.getByRole("radio", { name: /Самовывоз/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Курьерская доставка/ }));

    const reselect = await screen.findByLabelText(/^Дата и время доставки/);
    expect((reselect as HTMLSelectElement).value).toBe("");
  });

  it("400 «слот занят»: текст сервера показан, справочник перезапрошен, выбор сброшен", async () => {
    mockedPlaceOrder.mockRejectedValue(
      new ApiError("Это время уже занято — выберите другой интервал.", 400),
    );
    render(<CheckoutPage />);
    const select = await screen.findByLabelText(/^Дата и время доставки/);
    fillBaseFields();
    fireEvent.change(select, { target: { value: "11" } });
    const callsBefore = mockedGetSlots.mock.calls.length;
    submit();

    expect(await screen.findByText(/Это время уже занято/)).toBeTruthy();
    await waitFor(() =>
      expect(mockedGetSlots.mock.calls.length).toBeGreaterThan(callsBefore),
    );
    expect(
      ((await screen.findByLabelText(/^Дата и время доставки/)) as HTMLSelectElement).value,
    ).toBe("");
  });
});
