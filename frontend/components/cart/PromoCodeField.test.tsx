import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const useCartMock = vi.fn();
vi.mock("@/components/cart/CartProvider", () => ({
  useCart: () => useCartMock(),
}));

import { ApiError } from "@/lib/api";
import { PromoCodeField } from "./PromoCodeField";

function ctx(overrides: Record<string, unknown> = {}) {
  return {
    cart: {
      promotions_enabled: true,
      promo_code: "",
      promo_code_error: null,
      ...((overrides.cart as object) ?? {}),
    },
    applyPromo: vi.fn().mockResolvedValue({}),
    removePromo: vi.fn().mockResolvedValue({}),
    ...overrides,
  };
}

describe("PromoCodeField (#571)", () => {
  beforeEach(() => useCartMock.mockReset());

  it("применяет код через applyPromo и чистит поле", async () => {
    const value = ctx();
    useCartMock.mockReturnValue(value);
    render(<PromoCodeField />);

    fireEvent.change(screen.getByLabelText("Промокод"), { target: { value: " sale10 " } });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));

    await waitFor(() => expect(value.applyPromo).toHaveBeenCalledWith("sale10"));
  });

  it("400 от сервера показывает человеческий текст, код не прилипает", async () => {
    const value = ctx({
      applyPromo: vi.fn().mockRejectedValue(new ApiError("Такого промокода нет.", 400)),
    });
    useCartMock.mockReturnValue(value);
    render(<PromoCodeField />);

    fireEvent.change(screen.getByLabelText("Промокод"), { target: { value: "NOPE" } });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));

    expect(await screen.findByText("Такого промокода нет.")).toBeTruthy();
  });

  it("применённый код показан чипом и снимается крестиком", async () => {
    const value = ctx({ cart: { promotions_enabled: true, promo_code: "SALE10" } });
    useCartMock.mockReturnValue(value);
    render(<PromoCodeField />);

    expect(screen.getByText("SALE10")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Убрать промокод"));
    await waitFor(() => expect(value.removePromo).toHaveBeenCalled());
  });

  it("серверная ошибка применённого кода (истёк после применения) видна", () => {
    useCartMock.mockReturnValue(
      ctx({
        cart: {
          promotions_enabled: true,
          promo_code: "OLD",
          promo_code_error: { code: "expired", message: "Срок действия промокода истёк." },
        },
      }),
    );
    render(<PromoCodeField />);
    expect(screen.getByText("Срок действия промокода истёк.")).toBeTruthy();
  });

  it("не рендерится при выключенном флаге promotions", () => {
    useCartMock.mockReturnValue(ctx({ cart: { promotions_enabled: false } }));
    const { container } = render(<PromoCodeField />);
    expect(container.innerHTML).toBe("");
  });
});
