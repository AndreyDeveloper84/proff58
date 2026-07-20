import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Order } from "@/lib/types";
import { ReservationNotice } from "./ReservationNotice";

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
    reserved_until: new Date(Date.now() + 30 * 60_000).toISOString(),
    reservation_status: "held",
    reservation_expired: false,
    created_at: new Date().toISOString(),
    items: [],
    ...overrides,
  };
}

describe("ReservationNotice", () => {
  it("активный резерв: показывает «зарезервировано до …»", () => {
    render(<ReservationNotice order={order()} />);
    expect(screen.getByText(/Товар зарезервирован за вами до/)).toBeInTheDocument();
  });

  it("reservation_expired=true → expired-состояние", () => {
    render(<ReservationNotice order={order({ reservation_expired: true })} />);
    expect(screen.getByText(/Время резерва истекло/)).toBeInTheDocument();
  });

  it("released с прошедшим сроком → expired-состояние (janitor уже отработал)", () => {
    render(
      <ReservationNotice
        order={order({
          reservation_status: "released",
          reservation_expired: true,
          reserved_until: new Date(Date.now() - 60_000).toISOString(),
        })}
      />,
    );
    expect(screen.getByText(/Время резерва истекло/)).toBeInTheDocument();
  });

  it("скрыт для B2B (эквивалент — в счёте)", () => {
    const { container } = render(<ReservationNotice order={order({ customer_type: "b2b" })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("скрыт для оплаченного заказа", () => {
    const { container } = render(<ReservationNotice order={order({ payment_status: "paid" })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("скрыт для отменённого заказа (payment остаётся pending при отмене из 1С)", () => {
    const { container } = render(
      <ReservationNotice order={order({ fulfillment_status: "cancelled" })} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("скрыт для старого снимка без полей резерва", () => {
    const { container } = render(
      <ReservationNotice
        order={order({
          reserved_until: undefined,
          reservation_status: undefined,
          reservation_expired: undefined,
        })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  describe("автопереключение по времени", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("активная плашка переключается в expired после наступления reserved_until", () => {
      render(
        <ReservationNotice
          order={order({ reserved_until: new Date(Date.now() + 60_000).toISOString() })}
        />,
      );
      expect(screen.getByText(/Товар зарезервирован за вами до/)).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(2 * 60_000);
      });
      expect(screen.getByText(/Время резерва истекло/)).toBeInTheDocument();
    });
  });
});
