import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

const refreshMock = vi.fn();
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({
    cart: {
      lines: [{ id: 1, name: "Перфоратор", quantity: 1, line_total: "1000.00" }],
    },
    loading: false,
    total: 1000,
    refresh: refreshMock,
  }),
}));

vi.mock("@/lib/orders", () => ({ placeOrder: vi.fn() }));
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
