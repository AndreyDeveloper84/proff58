import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// #574: разбивка итога и честный fallback без снимка заказа.
// Номер в useParams приходит закодированным (Next отдаёт сегмент как в адресе),
// а checkout кладёт снимок под обычным номером — на этой паре и ломался поиск.
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "%D0%9F-1" }) }));
vi.mock("@/lib/order-storage", () => ({ readStashedOrder: vi.fn() }));
vi.mock("@/components/order/TrackOrderInMaxCta", () => ({
  TrackOrderInMaxCta: () => <div data-testid="max-cta" />,
}));
vi.mock("@/lib/orders", () => ({ getGuestOrder: vi.fn(), startOrderPayment: vi.fn() }));

import { readStashedOrder } from "@/lib/order-storage";
import { getGuestOrder } from "@/lib/orders";
import ThanksPage from "./page";

const mockedRead = readStashedOrder as unknown as ReturnType<typeof vi.fn>;
const mockedGuest = getGuestOrder as unknown as ReturnType<typeof vi.fn>;

function order(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    order_number: "П-1",
    display_status: "Новый",
    customer_type: "b2c",
    payment_status: "pending",
    fulfillment_status: "new",
    delivery_method: "courier",
    delivery_address: "Пенза, ул. Мира, 1",
    delivery_cost: "500.00",
    payment_method: "online",
    total: "1500.00",
    currency: "RUB",
    vat_rate: 0,
    vat_amount: "0.00",
    items: [{ id: 1, name: "Перфоратор", quantity: 1, line_total: "1000.00" }],
    ...overrides,
  };
}

describe("ThanksPage (#574)", () => {
  beforeEach(() => {
    mockedRead.mockReset();
    // Без снимка с токеном догрузки не будет — по умолчанию тесты её и не ждут.
    mockedGuest.mockReset();
    mockedGuest.mockResolvedValue(order());
  });

  it("итог разложен на товары и доставку", () => {
    mockedRead.mockReturnValue(order());
    render(<ThanksPage />);
    expect(screen.getByText("Товары")).toBeTruthy();
    expect(screen.getAllByText("Доставка").length).toBeGreaterThan(0);
    expect(screen.getByText("Итого:")).toBeTruthy();
  });

  it("неизвестная стоимость доставки — предварительный итог", () => {
    mockedRead.mockReturnValue(order({ delivery_cost: null }));
    render(<ThanksPage />);
    expect(screen.getByText("уточнит менеджер")).toBeTruthy();
    expect(screen.getByText("Предварительный итог:")).toBeTruthy();
  });

  it("НДС показывается только когда он выделен (B2B)", () => {
    mockedRead.mockReturnValue(order({ vat_rate: 22, vat_amount: "270.49" }));
    render(<ThanksPage />);
    expect(screen.getByText("В т.ч. НДС 22%")).toBeTruthy();
  });

  // Показывали сырой код: в деталях заказа стояло «cash».
  it("способ оплаты назван по-человечески", () => {
    mockedRead.mockReturnValue(order({ payment_method: "cash", delivery_method: "pickup" }));
    render(<ThanksPage />);
    expect(screen.getByText("Наличными при получении")).toBeTruthy();
    expect(screen.queryByText("cash")).toBeNull();
  });

  // Состояние заказа сообщает OrderOutcome сверху. Дублирующая строка «Статус»
  // спорила с ним: над «Оплата при получении» стояло «Ожидает оплаты».
  it("статус в деталях не дублируется", () => {
    mockedRead.mockReturnValue(
      order({ payment_method: "cash", delivery_method: "pickup", display_status: "Ожидает оплаты" }),
    );
    render(<ThanksPage />);
    expect(screen.getByText("Оплата при получении. Мы свяжемся с вами и сообщим об изменении статуса.")).toBeTruthy();
    expect(screen.queryByText("Ожидает оплаты")).toBeNull();
  });

  // Раньше без снимка страница показывала только номер заказа и ничего не объясняла.
  it("без снимка объясняет ситуацию и ведёт в кабинет", () => {
    mockedRead.mockReturnValue(null);
    render(<ThanksPage />);
    expect(screen.getByText(/Детали заказа не сохранились в этом браузере/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "в личном кабинете" })).toBeTruthy();
  });

  // Ключ снимка — обычный номер заказа. Пока его брали из useParams как есть,
  // поиск шёл по «%D0%9F-1» и не находил ничего: страница ВСЕГДА показывала
  // «детали не сохранились», а в заголовке светился закодированный номер.
  it("ищет снимок по раскодированному номеру", () => {
    mockedRead.mockReturnValue(null);
    render(<ThanksPage />);

    expect(mockedRead).toHaveBeenCalledWith("П-1");
    expect(screen.getByText(/№ П-1/)).toBeTruthy();
  });

  // DRF-951: гостевой ответ приходит БЕЗ access_token, и раньше он затирал снимок
  // целиком — кнопка «Отслеживать заказ в MAX» показывалась на секунду и исчезала,
  // как только догрузка доезжала. Токен обязан пережить слияние.
  it("догрузка свежего заказа не уносит кнопку MAX", async () => {
    mockedRead.mockReturnValue(order({ access_token: "guest-token" }));
    mockedGuest.mockResolvedValue(order({ payment_status: "paid" }));

    render(<ThanksPage />);
    // Дожидаемся именно свежих данных: заголовок меняется только по ответу сервера.
    await screen.findByText("Заказ оплачен");

    expect(screen.getByTestId("max-cta")).toBeTruthy();
  });

  it("без токена в снимке кнопки MAX нет", () => {
    mockedRead.mockReturnValue(order());
    render(<ThanksPage />);

    expect(screen.queryByTestId("max-cta")).toBeNull();
  });
});
