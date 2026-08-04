import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const replaceMock = vi.fn();

// Номер как он реально приходит из useParams: Next отдаёт сегмент закодированным,
// а все наши номера начинаются с кириллической «П». Раньше здесь стоял
// ASCII-номер, поэтому двойное кодирование в getOrder тесты не ловили.
const { ENCODED_NUMBER, ORDER_NUMBER } = vi.hoisted(() => ({
  ENCODED_NUMBER: "%D0%9F-20260803-CC74CA",
  ORDER_NUMBER: "П-20260803-CC74CA",
}));

// router — стабильный объект: новый на каждый рендер менял бы зависимости
// эффекта загрузки, и тот перезагружал бы заказ поверх свежих изменений.
const routerStub = { push: pushMock, replace: replaceMock };
vi.mock("next/navigation", () => ({
  useParams: () => ({ number: ENCODED_NUMBER }),
  useRouter: () => routerStub,
  usePathname: () => `/account/orders/${ENCODED_NUMBER}`,
}));
vi.mock("@/lib/auth", () => ({
  checkAuth: vi.fn(),
  loginHref: (next?: string) => (next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login"),
  getOrder: vi.fn(),
  cancelOrder: vi.fn(),
}));

import { cancelOrder, checkAuth, getOrder } from "@/lib/auth";
import OrderDetailsPage from "./page";

const mockedGetMe = checkAuth as unknown as ReturnType<typeof vi.fn>;
const mockedGetOrder = getOrder as unknown as ReturnType<typeof vi.fn>;
const mockedCancel = cancelOrder as unknown as ReturnType<typeof vi.fn>;

describe("OrderDetailsPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetOrder.mockReset();
    mockedCancel.mockReset();
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedGetOrder.mockResolvedValue({
      id: 10,
      order_number: ORDER_NUMBER,
      external_order_id: "",
      fulfillment_status: "confirmed",
      payment_status: "pending",
      sync_1c_status: "pending",
      display_status: "Подтверждён",
      can_cancel: true,
      customer_name: "Иван Иванов",
      customer_phone: "+79001112233",
      customer_email: "ivan@example.com",
      customer_type: "b2b",
      company_name: "ООО Инструмент",
      inn: "5800000000",
      kpp: "580001001",
      legal_address: "г. Пенза, ул. Ленина, 1",
      delivery_method: "courier",
      delivery_address: "г. Пенза, ул. Ленина, 1",
      delivery_zone: "city",
      delivery_cost: "500.00",
      delivery_calc_status: "calculated",
      comment: "Позвонить перед доставкой",
      payment_method: "invoice",
      total: "12500.00",
      vat_rate: 20,
      vat_amount: "2000.00",
      amount_without_vat: "10000.00",
      currency: "RUB",
      created_at: "2026-07-19T10:00:00Z",
      items: [
        {
          id: 1,
          product_id: 7,
          code_1c: "001",
          article: "DR-7",
          name: "Дрель аккумуляторная",
          unit: "шт.",
          price_base: "12000.00",
          price_final: "12000.00",
          discount: "0.00",
          price_type: "retail",
          currency: "RUB",
          quantity: 1,
          line_total: "12000.00",
        },
      ],
    });
  });

  it("показывает полный состав B2B-заказа и ссылку на счёт", async () => {
    render(<OrderDetailsPage />);

    expect(await screen.findByText("Дрель аккумуляторная")).toBeInTheDocument();
    expect(screen.getByText("ООО Инструмент")).toBeInTheDocument();
    expect(screen.getByText("В т.ч. НДС 20%")).toBeInTheDocument();
    expect(screen.getByText("Позвонить перед доставкой")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть счёт" })).toHaveAttribute(
      "href",
      `/api/orders/${encodeURIComponent(ORDER_NUMBER)}/invoice`,
    );
  });

  // Симптом со стенда: «Не удалось загрузить заказ» на каждой карточке. Номер из
  // useParams приходит закодированным, getOrder кодировал его повторно, и Django
  // искал заказ с номером «%D0%9F-…» — то есть 404 на любом заказе.
  it("запрашивает заказ по раскодированному номеру", async () => {
    render(<OrderDetailsPage />);

    expect(await screen.findByText("Дрель аккумуляторная")).toBeInTheDocument();
    expect(mockedGetOrder).toHaveBeenCalledWith(ORDER_NUMBER);
  });

  // --- Отмена заказа покупателем ---

  it("отменяет заказ только после подтверждения", async () => {
    mockedCancel.mockResolvedValue({
      ...(await mockedGetOrder()),
      fulfillment_status: "cancelled",
      display_status: "Отменён",
      can_cancel: false,
    });
    render(<OrderDetailsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Отменить заказ" }));
    // Один клик ничего не отменяет — сначала диалог.
    expect(mockedCancel).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Да, отменить заказ" }));

    await waitFor(() => expect(mockedCancel).toHaveBeenCalledWith(ORDER_NUMBER));
    expect(await screen.findByText("Отменён")).toBeInTheDocument();
    // Кнопки больше нет: отменять нечего, и повторное нажатие невозможно.
    expect(screen.queryByRole("button", { name: "Отменить заказ" })).toBeNull();
  });

  it("заказ, который отменять уже нельзя, кнопки не показывает", async () => {
    const order = await mockedGetOrder();
    mockedGetOrder.mockResolvedValue({ ...order, can_cancel: false });
    render(<OrderDetailsPage />);

    await screen.findByText("Дрель аккумуляторная");
    expect(screen.queryByRole("button", { name: "Отменить заказ" })).toBeNull();
  });

  // Между отрисовкой страницы и нажатием менеджер мог начать сборку: сервер
  // отвечает 409, и покупатель должен увидеть причину, а не молчание.
  it("отказ сервера показывает причину и оставляет заказ как был", async () => {
    mockedCancel.mockRejectedValue(
      new Error("Заказ уже в статусе «Собирается» — свяжитесь с менеджером."),
    );
    render(<OrderDetailsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Отменить заказ" }));
    fireEvent.click(screen.getByRole("button", { name: "Да, отменить заказ" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("свяжитесь с менеджером");
    expect(screen.getByText("Подтверждён")).toBeInTheDocument();
  });
});
