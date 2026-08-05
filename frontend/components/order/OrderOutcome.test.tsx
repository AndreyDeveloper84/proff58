import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Order } from "@/lib/types";
import { OrderOutcome } from "./OrderOutcome";

const startOrderPayment = vi.fn();
vi.mock("@/lib/orders", () => ({
  startOrderPayment: (...args: unknown[]) => startOrderPayment(...args),
}));

function order(overrides: Partial<Order> = {}): Order {
  return {
    id: 1,
    order_number: "О-100",
    external_order_id: "",
    fulfillment_status: "new",
    payment_status: "pending",
    sync_1c_status: "pending",
    display_status: "Новый",
    customer_name: "Иван",
    customer_phone: "+79990000001",
    customer_email: "",
    customer_type: "b2c",
    company_name: "",
    inn: "",
    kpp: "",
    legal_address: "",
    delivery_method: "courier",
    delivery_address: "",
    delivery_zone: "",
    delivery_cost: "0.00",
    delivery_calc_status: "calculated",
    comment: "",
    payment_method: "online",
    total: "1000.00",
    vat_rate: 0,
    vat_amount: "0.00",
    amount_without_vat: "0.00",
    currency: "RUB",
    reserved_until: null,
    reservation_status: "held",
    reservation_expired: false,
    created_at: new Date().toISOString(),
    items: [],
    access_token: "guest-token",
    ...overrides,
  };
}

beforeEach(() => {
  startOrderPayment.mockReset();
});

describe("OrderOutcome", () => {
  // Главное, ради чего блок переписан: до подтверждения кассы «Заказ оплачен»
  // писать нельзя — это обещание, за которым ничего не стоит.
  it("неоплаченный онлайн-заказ зовёт оплатить, а не поздравляет", () => {
    render(<OrderOutcome order={order()} orderNumber="О-100" />);

    expect(screen.getByText("Заказ оформлен, ожидает оплаты")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Оплатить заказ" })).toBeInTheDocument();
  });

  it("оплаченный заказ подтверждает оплату и кнопку не показывает", () => {
    render(<OrderOutcome order={order({ payment_status: "paid" })} orderNumber="О-100" />);

    expect(screen.getByText("Заказ оплачен")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
  });

  it("счёт для организации: оплаты онлайн нет, есть ссылка на счёт", () => {
    render(
      <OrderOutcome
        order={order({ payment_method: "invoice", customer_type: "b2b" })}
        orderNumber="О-100"
        invoiceHref="/account/invoices"
      />,
    );

    expect(screen.getByText("Счёт сформирован")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть счёт" })).toHaveAttribute(
      "href",
      "/account/invoices",
    );
    expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
  });

  it("оплата при получении — заказ принят без всякой кассы", () => {
    render(<OrderOutcome order={order({ payment_method: "cash" })} orderNumber="О-100" />);

    expect(screen.getByText("Заказ принят")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
  });

  // Касса легла — заказ уже оформлен, и человек должен это понимать,
  // а не думать, что потерял и деньги, и заказ.
  it("сбой оплаты объясняет, что заказ сохранён", async () => {
    startOrderPayment.mockRejectedValue(new Error("boom"));
    render(<OrderOutcome order={order()} orderNumber="О-100" />);

    fireEvent.click(screen.getByRole("button", { name: "Оплатить заказ" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/Заказ сохранён/),
    );
    expect(screen.getByRole("button", { name: "Оплатить заказ" })).toBeEnabled();
  });

  it("повторная оплата идёт по гостевому токену заказа", async () => {
    startOrderPayment.mockReturnValue(new Promise(() => {}));
    render(<OrderOutcome order={order()} orderNumber="О-100" />);

    fireEvent.click(screen.getByRole("button", { name: "Оплатить заказ" }));

    expect(startOrderPayment).toHaveBeenCalledWith("О-100", "guest-token");
    expect(screen.getByRole("button", { name: "Переходим к оплате…" })).toBeDisabled();
  });

  it("без снимка заказа показывает номер из адреса и не врёт про оплату", () => {
    render(<OrderOutcome order={null} orderNumber="О-777" />);

    expect(screen.getByText(/О-777/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
  });
});
