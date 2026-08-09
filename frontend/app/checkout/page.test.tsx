import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

const refreshMock = vi.fn();
const FULL_CART = {
  lines: [{ id: 1, name: "Перфоратор", quantity: 1, line_total: "1000.00" }],
};
// Снимок корзины меняется по ходу теста: после оформления бэкенд её закрывает,
// и провайдер отдаёт пустую — ровно тот момент, на котором ломался DRF-950.
const cartState = { cart: FULL_CART as { lines: unknown[] } | null, loading: false };
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({
    cart: cartState.cart,
    loading: cartState.loading,
    total: 1000,
    refresh: refreshMock,
  }),
}));

const startPaymentMock = vi.fn();
vi.mock("@/lib/orders", () => ({
  placeOrder: vi.fn(),
  startOrderPayment: (...args: unknown[]) => startPaymentMock(...args),
}));
vi.mock("@/lib/order-storage", () => ({ stashOrder: vi.fn() }));

import { placeOrder } from "@/lib/orders";
import CheckoutPage from "./page";

const mockedPlaceOrder = placeOrder as unknown as ReturnType<typeof vi.fn>;

/** Заполнить общие обязательные поля (физлицо, курьер). */
function fillBaseFields() {
  fireEvent.change(screen.getByLabelText(/^Имя/), { target: { value: "Иван" } });
  fireEvent.change(screen.getByLabelText(/^Телефон/), { target: { value: "+79001112233" } });
  // Адрес заполняется по частям — как на службах доставки (см. lib/delivery-address).
  fireEvent.change(screen.getByLabelText(/^Улица/), { target: { value: "Ленина" } });
  fireEvent.change(screen.getByLabelText(/^Дом/), { target: { value: "1" } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: /оформить/i }));
}

describe("CheckoutPage — B2B-реквизиты и способ оплаты", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    refreshMock.mockReset();
    cartState.cart = FULL_CART;
    cartState.loading = false;
    startPaymentMock.mockReset();
    startPaymentMock.mockResolvedValue({ payment_status: "pending", confirmation_url: "" });
    mockedPlaceOrder.mockReset();
    mockedPlaceOrder.mockResolvedValue({ order_number: "П-1" });
  });

  it("физлицо: отправляет payment_method=online", async () => {
    render(<CheckoutPage />);
    fillBaseFields();
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({
      customer_type: "b2c",
      payment_method: "online",
      // Части адреса склеиваются в одну строку — контракт заказа не менялся.
      delivery_address: "г. Пенза, Ленина, д. 1",
    });
  });

  // В базе стенда лежат заказы с адресом «Пен» и «Молокова»: одно поле «Адрес
  // доставки» принимало что угодно, и курьеру было некуда ехать.
  it("без номера дома заказ не отправляется", async () => {
    render(<CheckoutPage />);
    fireEvent.change(screen.getByLabelText(/^Имя/), { target: { value: "Иван" } });
    fireEvent.change(screen.getByLabelText(/^Телефон/), { target: { value: "+79001112233" } });
    fireEvent.change(screen.getByLabelText(/^Улица/), { target: { value: "Молокова" } });
    submit();

    expect(await screen.findByText(/номер дома/i)).toBeTruthy();
    expect(mockedPlaceOrder).not.toHaveBeenCalled();
  });

  it("B2B без КПП и юр. адреса: заказ не отправляется, показана ошибка", async () => {
    render(<CheckoutPage />);
    fillBaseFields();
    fireEvent.click(screen.getByLabelText("Организация"));
    fireEvent.change(screen.getByLabelText(/^Организация \*/), { target: { value: "ООО Ромашка" } });
    fireEvent.change(screen.getByLabelText(/^ИНН/), { target: { value: "7700000000" } });
    submit();

    // Бэк требует КПП для юрлица — раньше форма молча уходила в 400.
    expect(await screen.findByText(/КПП обязателен/i)).toBeTruthy();
    expect(mockedPlaceOrder).not.toHaveBeenCalled();
  });

  it("B2B заполненный: шлёт kpp, legal_address и payment_method=invoice", async () => {
    render(<CheckoutPage />);
    fillBaseFields();
    fireEvent.click(screen.getByLabelText("Организация"));
    fireEvent.change(screen.getByLabelText(/^Организация \*/), { target: { value: "ООО Ромашка" } });
    fireEvent.change(screen.getByLabelText(/^ИНН/), { target: { value: "7700000000" } });
    fireEvent.change(screen.getByLabelText(/^КПП/), { target: { value: "770001001" } });
    fireEvent.change(screen.getByLabelText(/^Юридический адрес/), {
      target: { value: "г. Пенза, ул. Ленина, 1" },
    });
    fireEvent.change(screen.getByLabelText(/^E-mail/), { target: { value: "buh@romashka.ru" } });
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({
      customer_type: "b2b",
      company_name: "ООО Ромашка",
      inn: "7700000000",
      kpp: "770001001",
      legal_address: "г. Пенза, ул. Ленина, 1",
      customer_email: "buh@romashka.ru",
      payment_method: "invoice",
      // #558 (Wave 1): доставки для юрлиц нет — всегда самовывоз без зоны/адреса.
      delivery_method: "pickup",
      delivery_zone: "",
      delivery_address: "",
    });
  });

  it("B2B: блок доставки скрыт, показано пояснение про самовывоз", () => {
    render(<CheckoutPage />);
    expect(screen.getByText("Способ доставки")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Организация"));
    expect(screen.queryByText("Способ доставки")).toBeNull();
    expect(screen.getByText(/самовывоз со склада/i)).toBeTruthy();
    expect(screen.getByText(/Счёт формируется только на товары/i)).toBeTruthy();
  });

  it("ИП (ИНН 12 цифр): КПП не требуется", async () => {
    render(<CheckoutPage />);
    fillBaseFields();
    fireEvent.click(screen.getByLabelText("Организация"));
    fireEvent.change(screen.getByLabelText(/^Организация \*/), { target: { value: "ИП Иванов" } });
    fireEvent.change(screen.getByLabelText(/^ИНН/), { target: { value: "770000000000" } });
    fireEvent.change(screen.getByLabelText(/^Юридический адрес/), {
      target: { value: "г. Пенза, ул. Ленина, 2" },
    });
    fireEvent.change(screen.getByLabelText(/^E-mail/), { target: { value: "ip@example.ru" } });
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({ kpp: "", payment_method: "invoice" });
  });
});

describe("CheckoutPage — DRF-950: корзина пустеет после оформления", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    refreshMock.mockReset();
    cartState.cart = FULL_CART;
    cartState.loading = false;
    startPaymentMock.mockReset();
    startPaymentMock.mockResolvedValue({ payment_status: "pending", confirmation_url: "" });
    mockedPlaceOrder.mockReset();
    mockedPlaceOrder.mockResolvedValue({ order_number: "П-950" });
  });

  // Первопричина бага: бэкенд закрывает корзину вместе с созданием заказа, и
  // сторож пустой корзины уводил покупателя в /cart. Заказ создан, а человек
  // видит «Корзина пуста» и жмёт «Оформить» второй раз.
  it("после успешного заказа ведёт на «Спасибо», а не в пустую корзину", async () => {
    const { rerender } = render(<CheckoutPage />);
    fillBaseFields();
    submit();

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/order/П-950/thanks"));

    // Корзина опустела — так и должно быть после оформления.
    cartState.cart = { lines: [] };
    rerender(<CheckoutPage />);

    expect(replaceMock).not.toHaveBeenCalledWith("/cart");
  });

  it("заход с пустой корзиной по-прежнему уводит в /cart", () => {
    cartState.cart = { lines: [] };
    render(<CheckoutPage />);

    expect(replaceMock).toHaveBeenCalledWith("/cart");
  });

  it("переход на «Спасибо» не ждёт обновления счётчика корзины", async () => {
    // refresh() висит — покупатель всё равно должен уехать на success.
    refreshMock.mockReturnValue(new Promise(() => {}));
    render(<CheckoutPage />);
    fillBaseFields();
    submit();

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/order/П-950/thanks"));
  });
});

describe("CheckoutPage — переход к оплате", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    refreshMock.mockReset();
    cartState.cart = FULL_CART;
    cartState.loading = false;
    startPaymentMock.mockReset();
    startPaymentMock.mockResolvedValue({ payment_status: "pending", confirmation_url: "" });
    mockedPlaceOrder.mockReset();
    mockedPlaceOrder.mockResolvedValue({ order_number: "П-777", access_token: "tok" });
  });

  it("онлайн-заказ запрашивает ссылку на оплату по номеру и токену", async () => {
    render(<CheckoutPage />);
    fillBaseFields();
    submit();

    await waitFor(() => expect(startPaymentMock).toHaveBeenCalledWith("П-777", "tok"));
  });

  // Касса выключена или лежит — заказ уже оформлен, и человек должен попасть
  // на страницу «Спасибо», а не остаться на checkout с ошибкой.
  it("сбой кассы всё равно ведёт на «Спасибо»", async () => {
    startPaymentMock.mockRejectedValue(new Error("касса недоступна"));
    render(<CheckoutPage />);
    fillBaseFields();
    submit();

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/order/П-777/thanks"));
  });
});

describe("CheckoutPage — способы оплаты (DRF-948)", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    refreshMock.mockReset();
    cartState.cart = FULL_CART;
    cartState.loading = false;
    startPaymentMock.mockReset();
    startPaymentMock.mockResolvedValue({ payment_status: "pending", confirmation_url: "" });
    mockedPlaceOrder.mockReset();
    mockedPlaceOrder.mockResolvedValue({ order_number: "П-948" });
  });

  const pickSelfPickup = () =>
    fireEvent.click(screen.getByRole("radio", { name: /самовывоз/i }));

  it("самовывоз: доступны онлайн, наличные и карта при получении", () => {
    render(<CheckoutPage />);
    pickSelfPickup();

    expect(screen.getByRole("radio", { name: /Онлайн-оплата/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Наличными при получении/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Картой при получении/ })).toBeInTheDocument();
  });

  // Оплату курьеру магазин не подтверждал: показывать её нельзя даже
  // заблокированной — это выглядит как обещание.
  it("курьер: только онлайн, оплаты на месте нет", () => {
    render(<CheckoutPage />);

    expect(screen.getByRole("radio", { name: /Онлайн-оплата/ })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /при получении/ })).not.toBeInTheDocument();
  });

  it("выбранные наличные уходят в заказ", async () => {
    render(<CheckoutPage />);
    pickSelfPickup();
    fireEvent.click(screen.getByRole("radio", { name: /Наличными при получении/ }));
    fireEvent.change(screen.getByLabelText(/^Имя/), { target: { value: "Иван" } });
    fireEvent.change(screen.getByLabelText(/^Телефон/), { target: { value: "+79001112233" } });
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({ payment_method: "cash" });
  });

  // Выбрали карту на самовывозе, потом передумали и выбрали курьера — такой
  // способ исчез, и заказ не должен уйти с заведомо невозможной оплатой.
  it("смена получения на курьера возвращает оплату к онлайн", async () => {
    render(<CheckoutPage />);
    pickSelfPickup();
    fireEvent.click(screen.getByRole("radio", { name: /Картой при получении/ }));
    fireEvent.click(screen.getByRole("radio", { name: /курьер/i }));
    fillBaseFields();
    submit();

    await waitFor(() => expect(mockedPlaceOrder).toHaveBeenCalled());
    expect(mockedPlaceOrder.mock.calls[0][0]).toMatchObject({ payment_method: "online" });
  });

  it("организация платит только по счёту", () => {
    render(<CheckoutPage />);
    fireEvent.click(screen.getByRole("radio", { name: /Организация|Юридическое/i }));

    expect(screen.getByRole("radio", { name: /Оплата по счёту/ })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Онлайн-оплата/ })).not.toBeInTheDocument();
  });
});
