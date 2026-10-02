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

  // DRF-2299: пока доставка не рассчитана, итог предварительный — кнопки нет,
  // а причина названа прямо.
  it("онлайн-заказ с нерассчитанной доставкой не зовёт оплатить", () => {
    render(
      <OrderOutcome
        order={order({ delivery_calc_status: "manual_required", delivery_cost: null })}
        orderNumber="О-100"
      />,
    );

    expect(screen.getByText("Заказ принят, стоимость доставки уточняется")).toBeInTheDocument();
    expect(screen.getByText(/на сумму/)).toHaveTextContent(/\(без доставки\)/);
    expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
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

  // Наличные и карта на выдаче — одна и та же договорённость «плачу в магазине».
  // Карта долго проваливалась в ветку онлайна и звала в кассу.
  it.each(["cash", "card_on_pickup"])(
    "оплата при получении (%s) — заказ принят без всякой кассы",
    (method) => {
      render(<OrderOutcome order={order({ payment_method: method })} orderNumber="О-100" />);

      expect(screen.getByText("Заказ принят")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
    },
  );

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

  // DRF-2736: страница оплаты у кассы живёт дольше резерва. Покупатель возвращался
  // к уже отменённому заказу и видел «ожидает оплаты» с кнопкой «Оплатить».
  describe("отменённый заказ", () => {
    it("автоотмена по неоплате: причина названа, платить не зовём", () => {
      render(
        <OrderOutcome
          order={order({ fulfillment_status: "cancelled", payment_status: "expired" })}
          orderNumber="О-100"
        />,
      );

      expect(screen.getByRole("heading", { name: "Заказ отменён" })).toBeInTheDocument();
      expect(screen.getByText(/Оплата не поступила в срок/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
    });

    it("отменён покупателем или менеджером: платить не зовём, причину не выдумываем", () => {
      render(
        <OrderOutcome
          order={order({ fulfillment_status: "cancelled", payment_status: "pending" })}
          orderNumber="О-100"
        />,
      );

      expect(screen.getByRole("heading", { name: "Заказ отменён" })).toBeInTheDocument();
      expect(screen.queryByText(/не поступила в срок/)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
    });

    it.each(["paid", "partially_refunded"] as const)(
      "оплата после отмены (%s): деньги вернём, заявка уже есть",
      (payment_status) => {
        render(
          <OrderOutcome
            order={order({ fulfillment_status: "cancelled", payment_status })}
            orderNumber="О-100"
          />,
        );

        expect(
          screen.getByRole("heading", { name: "Заказ отменён, оплата получена" }),
        ).toBeInTheDocument();
        expect(screen.getByText(/Заявка на возврат создана автоматически/)).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "контакты" })).toHaveAttribute(
          "href",
          "/info/about",
        );
        // «Заказ оплачен, начали собирать» по отменённому заказу — неправда.
        expect(screen.queryByText("Заказ оплачен")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
      },
    );

    // Счёт организации оплачен переводом: автоматической заявки на возврат нет,
    // обещать её нельзя.
    it("оплата не через кассу: про автоматическую заявку не говорим", () => {
      render(
        <OrderOutcome
          order={order({
            fulfillment_status: "cancelled",
            payment_status: "paid",
            payment_method: "invoice",
          })}
          orderNumber="О-100"
          invoiceHref="/account/invoices"
        />,
      );

      expect(
        screen.getByRole("heading", { name: "Заказ отменён, оплата получена" }),
      ).toBeInTheDocument();
      expect(screen.getByText(/Мы свяжемся с вами, чтобы вернуть деньги/)).toBeInTheDocument();
      expect(screen.queryByText(/создана автоматически/)).not.toBeInTheDocument();
    });

    it("деньги уже возвращены — так и пишем", () => {
      render(
        <OrderOutcome
          order={order({ fulfillment_status: "cancelled", payment_status: "refunded" })}
          orderNumber="О-100"
        />,
      );

      expect(
        screen.getByRole("heading", { name: "Заказ отменён, деньги возвращены" }),
      ).toBeInTheDocument();
    });

    // Отмена важнее способа оплаты: «Счёт сформирован» и «Заказ принят» по
    // отменённому заказу так же неверны, как «ожидает оплаты».
    it.each(["invoice", "cash"])("отмена важнее способа оплаты (%s)", (payment_method) => {
      render(
        <OrderOutcome
          order={order({ fulfillment_status: "cancelled", payment_method })}
          orderNumber="О-100"
          invoiceHref="/account/invoices"
        />,
      );

      expect(screen.getByRole("heading", { name: "Заказ отменён" })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Открыть счёт" })).not.toBeInTheDocument();
    });
  });

  it("без снимка заказа показывает номер из адреса и не врёт про оплату", () => {
    render(<OrderOutcome order={null} orderNumber="О-777" />);

    expect(screen.getByText(/О-777/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Оплатить заказ" })).not.toBeInTheDocument();
  });
});
