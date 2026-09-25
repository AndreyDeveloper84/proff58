import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => ({
    cart: { lines: [{ id: 1, name: "Перфоратор", quantity: 1, line_total: "1000.00" }] },
    loading: false,
    total: 1000,
    refresh: vi.fn(),
  }),
}));
vi.mock("@/lib/orders", () => ({ placeOrder: vi.fn(), startOrderPayment: vi.fn() }));
vi.mock("@/lib/order-storage", () => ({ stashOrder: vi.fn() }));
vi.mock("@/lib/delivery", () => ({
  getDeliveryZones: vi.fn().mockResolvedValue([]),
  getDeliverySlots: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/lib/auth", () => ({ getMe: vi.fn() }));

import { getMe } from "@/lib/auth";
import CheckoutPage from "./page";

const mockedGetMe = getMe as unknown as ReturnType<typeof vi.fn>;

// Тип покупателя — выбор на форме; умолчание переключателя берётся из аккаунта,
// чтобы организация не оформила розницу, забыв щёлкнуть «Организация».
describe("CheckoutPage — умолчание типа покупателя", () => {
  beforeEach(() => mockedGetMe.mockClear());

  it("аккаунт-организация стартует с «Организация»", async () => {
    mockedGetMe.mockImplementation(() => Promise.resolve({ id: 1, customer_type: "b2b" }));
    render(<CheckoutPage />);
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: /Организация/ })).toBeChecked(),
    );
  });

  it("физлицо и гость стартуют с «Физическое лицо»", async () => {
    mockedGetMe.mockImplementation(() => Promise.resolve(null));
    render(<CheckoutPage />);
    await waitFor(() => expect(mockedGetMe).toHaveBeenCalled());
    expect(screen.getByRole("radio", { name: /Физическое лицо/ })).toBeChecked();
  });
});
