import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

const useCartMock = vi.fn();
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => useCartMock(),
}));
// Recommendations тянет каталог — в юнит-тесте не нужен.
vi.mock("@/components/home/Recommendations", () => ({
  Recommendations: () => null,
}));

import CartPage from "./page";

function makeCart(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    status: "active",
    currency: "RUB",
    total: "0.00",
    has_mixed_currencies: false,
    lines: [
      {
        id: 1,
        product_id: 5,
        name: "Перфоратор",
        slug: "perforator",
        quantity: 1,
        price_final: "1000.00",
        price_base: "1000.00",
        discount: null,
        price_type: "retail",
        currency: "RUB",
        line_total: "1000.00",
      },
    ],
    ...overrides,
  };
}

describe("CartPage — смешение валют (#375)", () => {
  beforeEach(() => useCartMock.mockReset());

  it("обычная корзина: предупреждения нет, ссылка на оформление активна", () => {
    useCartMock.mockReturnValue({
      cart: makeCart({ total: "1000.00" }),
      loading: false,
      total: 1000,
      update: vi.fn(),
      remove: vi.fn(),
    });
    render(<CartPage />);

    expect(screen.queryByText(/разных валютах/)).toBeNull();
    expect(screen.getAllByRole("link", { name: /оформлени/i }).length).toBeGreaterThan(0);
  });

  it("смешение валют: показано предупреждение, оформление заблокировано, «0 ₽» не рисуем", () => {
    // Бэк (services.get_cart_view) при смешении валют обнуляет total и поднимает флаг.
    // Раньше фронт молча показывал «Итого: 0 ₽» с активной кнопкой оформления.
    useCartMock.mockReturnValue({
      cart: makeCart({ has_mixed_currencies: true, total: "0.00" }),
      loading: false,
      total: 0,
      update: vi.fn(),
      remove: vi.fn(),
    });
    render(<CartPage />);

    expect(screen.getAllByText(/разных валютах/).length).toBeGreaterThan(0);
    // Ссылок на /checkout нет — вместо них неактивные плашки.
    expect(screen.queryByRole("link", { name: /оформлени/i })).toBeNull();
    expect(screen.queryByText("0 ₽")).toBeNull();
  });
});
