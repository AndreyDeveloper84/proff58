import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CartLine } from "@/lib/types";
import { CartItemRow } from "./CartItemRow";

const line: CartLine = {
  id: 5,
  product_id: 42,
  name: "Аккумуляторная дрель",
  slug: "akkumulyatornaya-drel",
  quantity: 2,
  price_final: "12990.00",
  price_base: "13990.00",
  discount: "1000.00",
  price_type: "retail",
  currency: "RUB",
  line_total: "25980.00",
};

describe("CartItemRow", () => {
  it("показывает товар, количество, цены и выбранное состояние", () => {
    render(
      <CartItemRow
        line={line}
        selected
        onSelect={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    expect(screen.getByText("Аккумуляторная дрель")).toBeInTheDocument();
    expect(screen.getByText("Код товара: 42")).toBeInTheDocument();
    expect(screen.getAllByText("25 980 ₽").length).toBeGreaterThan(0);
    expect(screen.getByRole("checkbox", { name: "Выбрать Аккумуляторная дрель" })).toBeChecked();
  });

  it("вызывает обработчики выбора, количества и удаления", () => {
    const onSelect = vi.fn();
    const onUpdate = vi.fn();
    const onRemove = vi.fn();
    render(
      <CartItemRow
        line={line}
        selected={false}
        onSelect={onSelect}
        onUpdate={onUpdate}
        onRemove={onRemove}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "Выбрать Аккумуляторная дрель" }));
    fireEvent.click(screen.getByRole("button", { name: "Увеличить количество" }));
    fireEvent.click(screen.getByRole("button", { name: "Уменьшить количество" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Удалить Аккумуляторная дрель из корзины" }),
    );

    expect(onSelect).toHaveBeenCalledWith(5, true);
    expect(onUpdate).toHaveBeenNthCalledWith(1, 5, 3);
    expect(onUpdate).toHaveBeenNthCalledWith(2, 5, 1);
    expect(onRemove).toHaveBeenCalledWith(5);
  });
});
