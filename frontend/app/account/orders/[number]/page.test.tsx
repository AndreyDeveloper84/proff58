import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ number: "P-2026-0010" }),
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  usePathname: () => "/account/orders/P-2026-0010",
}));
vi.mock("@/lib/auth", () => ({
  checkAuth: vi.fn(),
  loginHref: (next?: string) => (next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login"),
  getOrder: vi.fn(),
}));

import { checkAuth, getOrder } from "@/lib/auth";
import OrderDetailsPage from "./page";

const mockedGetMe = checkAuth as unknown as ReturnType<typeof vi.fn>;
const mockedGetOrder = getOrder as unknown as ReturnType<typeof vi.fn>;

describe("OrderDetailsPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetOrder.mockReset();
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedGetOrder.mockResolvedValue({
      id: 10,
      order_number: "P-2026-0010",
      external_order_id: "",
      fulfillment_status: "confirmed",
      payment_status: "pending",
      sync_1c_status: "pending",
      display_status: "Подтверждён",
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
      "/api/orders/P-2026-0010/invoice",
    );
  });
});
