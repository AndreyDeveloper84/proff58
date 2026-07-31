import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  usePathname: () => "/account/invoices",
}));
vi.mock("@/lib/auth", () => ({
  checkAuth: vi.fn(),
  loginHref: (next?: string) => (next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login"),
}));
vi.mock("@/lib/invoices", () => ({ getInvoices: vi.fn() }));

import { checkAuth } from "@/lib/auth";
import { getInvoices } from "@/lib/invoices";
import InvoicesPage from "./page";

const mockedGetMe = checkAuth as unknown as ReturnType<typeof vi.fn>;
const mockedGetInvoices = getInvoices as unknown as ReturnType<typeof vi.fn>;

const B2B_USER = {
  id: 1,
  phone: "+79001112233",
  email: "buh@romashka.ru",
  full_name: "Иван",
  customer_type: "b2b",
  profile: null,
};

function invoice(overrides: Record<string, unknown> = {}) {
  return {
    number: "СЧ-П-20260720-AB12",
    status: "issued",
    status_display: "Выставлен",
    order_number: "П-20260720-AB12",
    order_display_status: "Новый",
    fulfillment_status: "new",
    payment_status: "pending",
    goods_total: "2000.00",
    vat_rate: 22,
    vat_amount: "360.66",
    amount_without_vat: "1639.34",
    total: "2000.00",
    currency: "RUB",
    issued_at: "2026-07-20T12:00:00+03:00",
    valid_until: "2026-07-21T12:00:00+03:00",
    is_expired: false,
    invoice_url: "/api/orders/П-20260720-AB12/invoice/",
    ...overrides,
  };
}

describe("InvoicesPage (#560)", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetInvoices.mockReset();
    mockedGetMe.mockResolvedValue(B2B_USER);
  });

  it("действующий счёт: номер, суммы, срок и ссылка на скачивание", async () => {
    mockedGetInvoices.mockResolvedValue([invoice()]);
    render(<InvoicesPage />);

    expect(await screen.findByText("СЧ-П-20260720-AB12")).toBeTruthy();
    expect(screen.getByText("Выставлен")).toBeTruthy();
    expect(screen.getByText(/в т.ч. НДС 22%/i)).toBeTruthy();
    expect(screen.getByText(/Счёт действителен до/)).toBeTruthy();
    const link = screen.getByRole("link", { name: /открыть счёт/i });
    expect(link.getAttribute("href")).toBe("/api/orders/П-20260720-AB12/invoice/");
  });

  it("истёкший счёт: бейдж «Истёк», пояснение, без кнопки скачивания", async () => {
    mockedGetInvoices.mockResolvedValue([
      invoice({ status: "expired", status_display: "Истёк", is_expired: true }),
    ]);
    render(<InvoicesPage />);

    expect(await screen.findByText("Истёк")).toBeTruthy();
    expect(screen.getByText(/заказ отменён, резерв товара снят/i)).toBeTruthy();
    expect(screen.queryByRole("link", { name: /открыть счёт/i })).toBeNull();
  });

  it("срок вышел до janitor'а (issued + is_expired): показываем «Истёк»", async () => {
    mockedGetInvoices.mockResolvedValue([invoice({ is_expired: true })]);
    render(<InvoicesPage />);

    expect(await screen.findByText("Истёк")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /открыть счёт/i })).toBeNull();
  });

  it("пустое состояние для B2C объясняет, откуда берутся счета", async () => {
    mockedGetMe.mockResolvedValue({ ...B2B_USER, customer_type: "b2c" });
    mockedGetInvoices.mockResolvedValue([]);
    render(<InvoicesPage />);

    expect(await screen.findByText("Счетов пока нет")).toBeTruthy();
    expect(screen.getByText(/заказам организаций/i)).toBeTruthy();
  });

  it("гость уводится на логин", async () => {
    mockedGetMe.mockResolvedValue("anonymous");
    mockedGetInvoices.mockResolvedValue([]);
    render(<InvoicesPage />);

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/account/login?next=%2Faccount%2Finvoices"));
  });
});
