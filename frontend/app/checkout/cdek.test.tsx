import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// DRF-2491: доставка СДЭК на чекауте — город, пункт выдачи или курьер, расчёт,
// запасной режим без СДЭК и пересчёт после 409.
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({
    cart: {
      lines: [{ id: 1, product_id: 7, name: "Перфоратор", quantity: 1, line_total: "1000.00" }],
      currency: "RUB",
      grand_total: "1000.00",
    },
    loading: false,
    total: 1000,
    refresh: vi.fn(),
  }),
}));
vi.mock("@/components/cart/PromoCodeField", () => ({ PromoCodeField: () => null }));
vi.mock("@/lib/orders", () => ({ placeOrder: vi.fn(), startOrderPayment: vi.fn() }));
vi.mock("@/lib/order-storage", () => ({ stashOrder: vi.fn() }));
vi.mock("@/lib/delivery", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/delivery")>()),
  getDeliveryZones: vi.fn(),
  getDeliverySlots: vi.fn(),
  searchCdekCities: vi.fn(),
  getCdekPoints: vi.fn(),
  quoteCdekDelivery: vi.fn(),
}));

import { ApiError } from "@/lib/api";
import {
  getCdekPoints,
  getDeliverySlots,
  getDeliveryZones,
  quoteCdekDelivery,
  searchCdekCities,
} from "@/lib/delivery";
import { placeOrder, startOrderPayment } from "@/lib/orders";
import CheckoutPage from "./page";

const mockedPlaceOrder = placeOrder as unknown as ReturnType<typeof vi.fn>;
const mockedStartPayment = startOrderPayment as unknown as ReturnType<typeof vi.fn>;
const mockedGetZones = getDeliveryZones as unknown as ReturnType<typeof vi.fn>;
const mockedGetSlots = getDeliverySlots as unknown as ReturnType<typeof vi.fn>;
const mockedCities = searchCdekCities as unknown as ReturnType<typeof vi.fn>;
const mockedPoints = getCdekPoints as unknown as ReturnType<typeof vi.fn>;
const mockedQuote = quoteCdekDelivery as unknown as ReturnType<typeof vi.fn>;

const ZONES = [
  { zone: "penza", name: "Пенза (курьер)", type: "courier", cost: "500.00", free_delivery: false },
  {
    zone: "cdek",
    name: "СДЭК по России",
    type: "courier",
    cost: null,
    free_delivery: false,
    is_external: true,
    carrier_available: true,
  },
];
const MOSCOW = { code: 44, name: "Москва", full_name: "Москва, Россия" };
const POINTS = [
  {
    code: "MSK1",
    name: "На Тверской",
    address: "ул. Тверская, 1",
    work_time: "Пн-Вс 10:00-21:00",
    latitude: null,
    longitude: null,
  },
  {
    code: "MSK2",
    name: "На Арбате",
    address: "ул. Арбат, 5",
    work_time: "Пн-Пт 09:00-20:00",
    latitude: null,
    longitude: null,
  },
];

function quote(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    data: {
      quote_id: "q1",
      status: "calculated",
      cost: "450.00",
      reason: "",
      period_min: 2,
      period_max: 4,
      address: "ул. Тверская, 1",
      city_name: "Москва",
      free_delivery_promo_applies: false,
      ...overrides,
    },
  };
}

function fillBaseFields() {
  fireEvent.change(screen.getByLabelText(/^Имя/), { target: { value: "Иван" } });
  fireEvent.change(screen.getByLabelText(/^Телефон/), { target: { value: "+79001112233" } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: /оформить/i }));
}

async function chooseCdekCity() {
  fireEvent.click(await screen.findByRole("radio", { name: /Доставка СДЭК по России/ }));
  fireEvent.change(screen.getByRole("combobox", { name: /Город/ }), { target: { value: "Мос" } });
  fireEvent.mouseDown(await screen.findByRole("option", { name: "Москва, Россия" }));
}

async function choosePoint(name: RegExp = /Тверская/) {
  fireEvent.click(await screen.findByRole("radio", { name }));
}

describe("CheckoutPage — доставка СДЭК (DRF-2491)", () => {
  beforeEach(() => {
    pushMock.mockClear();
    mockedPlaceOrder.mockReset();
    mockedPlaceOrder.mockResolvedValue({ order_number: "П-1", access_token: "t", items: [] });
    mockedStartPayment.mockReset();
    mockedStartPayment.mockResolvedValue({ confirmation_url: "" });
    mockedGetZones.mockReset();
    mockedGetZones.mockResolvedValue(ZONES);
    mockedGetSlots.mockReset();
    mockedGetSlots.mockResolvedValue([]);
    mockedCities.mockReset();
    mockedCities.mockResolvedValue({ ok: true, data: [MOSCOW] });
    mockedPoints.mockReset();
    mockedPoints.mockResolvedValue({ ok: true, data: POINTS });
    mockedQuote.mockReset();
    mockedQuote.mockResolvedValue(quote());
  });

  it("пункт выдачи: расчёт после выбора, цена в итоге, quote_id в заказе", async () => {
    render(<CheckoutPage />);
    await chooseCdekCity();
    await choosePoint();

    expect(await screen.findByText(/срок 2–4 дн\./)).toBeInTheDocument();
    expect(mockedQuote).toHaveBeenCalledWith({
      zone: "cdek",
      method: "cdek_pvz",
      city_code: 44,
      city_name: "Москва",
      pvz_code: "MSK1",
    });
    expect(screen.getByText("Доставка СДЭК:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Оформить заказ — 1\s450/ })).toBeInTheDocument();

    fillBaseFields();
    submit();
    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({
      delivery_method: "cdek_pvz",
      delivery_zone: "cdek",
      delivery_quote_id: "q1",
      delivery_address: "",
      delivery_slot_id: null,
      payment_method: "online",
    });
    expect(mockedStartPayment).toHaveBeenCalled();
  });

  it("курьер: расчёт по кнопке с адресом", async () => {
    mockedQuote.mockResolvedValue(quote({ quote_id: "q-courier", cost: "700.00" }));
    render(<CheckoutPage />);
    await chooseCdekCity();
    fireEvent.click(screen.getByRole("radio", { name: "Курьер до двери" }));
    fireEvent.change(screen.getByLabelText(/^Адрес доставки/), {
      target: { value: "ул. Ленина, 1, кв. 2" },
    });
    expect(mockedQuote).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Рассчитать доставку" }));

    expect(await screen.findByText(/срок 2–4 дн\./)).toBeInTheDocument();
    expect(mockedQuote.mock.calls[0][0]).toMatchObject({
      method: "cdek_courier",
      address: "ул. Ленина, 1, кв. 2",
    });

    fillBaseFields();
    submit();
    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({
      delivery_method: "cdek_courier",
      delivery_quote_id: "q-courier",
    });
  });

  it("без выбора пункта заказ не уходит", async () => {
    render(<CheckoutPage />);
    await chooseCdekCity();
    await screen.findByRole("radio", { name: /Тверская/ });
    fillBaseFields();
    submit();

    expect(await screen.findByText("Выберите пункт выдачи СДЭК.")).toBeInTheDocument();
    expect(mockedPlaceOrder).not.toHaveBeenCalled();
  });

  it("ручной расчёт: «уточнит менеджер», итог без доставки, оплата не стартует", async () => {
    mockedQuote.mockResolvedValue(
      quote({ status: "manual_required", cost: null, reason: "missing_package" }),
    );
    mockedPlaceOrder.mockResolvedValue({
      order_number: "П-2",
      access_token: "t",
      delivery_calc_status: "manual_required",
      items: [],
    });
    render(<CheckoutPage />);
    await chooseCdekCity();
    await choosePoint();

    expect(
      await screen.findByText(/Стоимость доставки этой посылки рассчитает менеджер/),
    ).toBeInTheDocument();
    expect(screen.getByText("уточнит менеджер после оформления")).toBeInTheDocument();
    expect(screen.getByText(/Без доставки: её стоимость рассчитает менеджер/)).toBeInTheDocument();

    fillBaseFields();
    submit();
    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({ delivery_quote_id: "q1" });
    expect(mockedStartPayment).not.toHaveBeenCalled();
    expect(pushMock).toHaveBeenCalledWith("/order/П-2/thanks");
  });

  it("СДЭК недоступен: город и адрес вручную, заказ уходит без расчёта", async () => {
    mockedCities.mockResolvedValue({
      ok: false,
      kind: "unavailable",
      message: "Доставка СДЭК сейчас недоступна.",
    });
    render(<CheckoutPage />);
    fireEvent.click(await screen.findByRole("radio", { name: /Доставка СДЭК по России/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Город/ }), { target: { value: "Каз" } });

    expect(await screen.findByText(/Расчёт СДЭК сейчас недоступен/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Город/), { target: { value: "Казань" } });
    fireEvent.change(screen.getByLabelText(/^Адрес или пункт выдачи/), {
      target: { value: "ул. Баумана, 1" },
    });
    expect(screen.getByText("уточнит менеджер после оформления")).toBeInTheDocument();

    fillBaseFields();
    submit();
    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    const payload = mockedPlaceOrder.mock.calls[0][0];
    expect(payload).toMatchObject({
      delivery_method: "cdek_pvz",
      delivery_zone: "cdek",
      delivery_address: "Казань, ул. Баумана, 1",
    });
    expect(payload.delivery_quote_id).toBeUndefined();
  });

  it("пункт не принимает вес: ошибка у списка пунктов", async () => {
    mockedQuote.mockResolvedValue({
      ok: false,
      kind: "invalid",
      field: "pvz_code",
      message: "Пункт выдачи принимает посылки до 5 кг — выберите другой пункт или доставку курьером.",
    });
    render(<CheckoutPage />);
    await chooseCdekCity();
    await choosePoint();

    expect(await screen.findByText(/принимает посылки до 5 кг/)).toBeInTheDocument();
    fillBaseFields();
    submit();
    expect(mockedPlaceOrder).not.toHaveBeenCalled();
  });

  it("409 «расчёт устарел»: пересчёт и новая цена, заказ повторно сам не уходит", async () => {
    mockedPlaceOrder.mockRejectedValueOnce(
      new ApiError("Расчёт доставки устарел.", 409, "delivery_quote_expired"),
    );
    render(<CheckoutPage />);
    await chooseCdekCity();
    await choosePoint();
    await screen.findByText(/срок 2–4 дн\./);
    mockedQuote.mockResolvedValue(quote({ quote_id: "q2", cost: "520.00" }));

    fillBaseFields();
    submit();

    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(alert).toHaveTextContent(/Стоимость доставки пересчитана: 520/));
    expect(mockedPlaceOrder).toHaveBeenCalledTimes(1);

    submit();
    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalledTimes(2));
    expect(mockedPlaceOrder.mock.calls[1][0]).toMatchObject({ delivery_quote_id: "q2" });
  });

  it("второй 409 подряд: ручной расчёт с тем, что уже выбрано", async () => {
    const conflict = new ApiError("Расчёт доставки устарел.", 409, "delivery_quote_expired");
    mockedPlaceOrder.mockRejectedValueOnce(conflict).mockRejectedValueOnce(conflict);
    render(<CheckoutPage />);
    await chooseCdekCity();
    await choosePoint();
    await screen.findByText(/срок 2–4 дн\./);
    fillBaseFields();

    submit();
    await screen.findByText(/Стоимость доставки пересчитана/);
    submit();

    expect(await screen.findByText(/Не удалось закрепить стоимость доставки СДЭК/)).toBeTruthy();
    expect(screen.getByLabelText(/^Город/)).toHaveValue("Москва");
    expect(screen.getByLabelText(/^Адрес или пункт выдачи/)).toHaveValue(
      "пункт выдачи MSK1, ул. Тверская, 1",
    );
  });

  it("сводка называет способ: «СДЭК, пункт выдачи»", async () => {
    render(<CheckoutPage />);
    fireEvent.click(await screen.findByRole("radio", { name: /Доставка СДЭК по России/ }));
    const summary = screen.getByText("Получение").closest("div") as HTMLElement;
    expect(within(summary).getByText("СДЭК, пункт выдачи")).toBeInTheDocument();
    // Для СДЭК только онлайн-оплата, слоты своего курьера не показываются.
    expect(screen.queryByRole("radio", { name: /Наличными/ })).toBeNull();
    expect(screen.queryByLabelText(/Дата и время доставки/)).toBeNull();
  });
});
