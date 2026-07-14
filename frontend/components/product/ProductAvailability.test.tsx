import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProductAvailability } from "./ProductAvailability";
import { LOW_STOCK_THRESHOLD } from "@/lib/constants";

// Наличие: базовые состояния in/order/out + производное «Мало осталось» по остатку (stockQty).
describe("ProductAvailability", () => {
  it("показывает «В наличии» без остатка", () => {
    render(<ProductAvailability stock="in" />);
    expect(screen.getByText("В наличии")).toBeInTheDocument();
  });

  it("показывает «Мало осталось» при остатке ниже порога", () => {
    render(<ProductAvailability stock="in" stockQty={LOW_STOCK_THRESHOLD} />);
    expect(screen.getByText("Мало осталось")).toBeInTheDocument();
  });

  it("остаётся «В наличии» при остатке выше порога", () => {
    render(<ProductAvailability stock="in" stockQty={LOW_STOCK_THRESHOLD + 1} />);
    expect(screen.getByText("В наличии")).toBeInTheDocument();
  });

  it("не показывает «Мало» для под-заказ (остаток игнорируется)", () => {
    render(<ProductAvailability stock="order" stockQty={1} />);
    expect(screen.getByText("Под заказ")).toBeInTheDocument();
  });

  it("фолбэк «Уточняйте наличие» без stock", () => {
    render(<ProductAvailability />);
    expect(screen.getByText("Уточняйте наличие")).toBeInTheDocument();
  });
});
