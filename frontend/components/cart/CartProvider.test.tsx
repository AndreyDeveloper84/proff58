import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/cart", () => ({
  getCart: vi.fn(),
  addToCart: vi.fn(),
  updateItem: vi.fn(),
  removeItem: vi.fn(),
  applyPromoCode: vi.fn(),
  removePromoCode: vi.fn(),
}));

import { subscribeActionSuccess } from "@/lib/action-feedback";
import { addToCart, getCart, removeItem, updateItem } from "@/lib/cart";
import type { Cart } from "@/lib/types";
import { CartProvider, useCart } from "./CartProvider";

const mockedGet = getCart as unknown as ReturnType<typeof vi.fn>;
const mockedAdd = addToCart as unknown as ReturnType<typeof vi.fn>;
const mockedUpdate = updateItem as unknown as ReturnType<typeof vi.fn>;
const mockedRemove = removeItem as unknown as ReturnType<typeof vi.fn>;

function cartWith(quantity: number): Cart {
  return {
    id: 1,
    lines: quantity
      ? [{ id: 10, product_id: 7, quantity } as unknown as Cart["lines"][number]]
      : [],
    total: "100",
  } as unknown as Cart;
}

// Мутации дёргаем кнопками, как это делают AddToCartButton/страница корзины;
// ошибка add уходит вызову — здесь её ловим и показываем текстом.
function Probe() {
  const { loading, count, add, update, remove } = useCart();
  const [status, setStatus] = useState("");
  return (
    <div>
      <span>{loading ? "грузим" : `count:${count}`}</span>
      <span>{status}</span>
      <button
        type="button"
        onClick={() =>
          add(7, 1)
            .then(() => setStatus("ok"))
            .catch(() => setStatus("ошибка"))
        }
      >
        add
      </button>
      <button type="button" onClick={() => update(10, 5)}>
        update
      </button>
      <button type="button" onClick={() => remove(10)}>
        remove
      </button>
    </div>
  );
}

// Корзина в шапке отыгрывает добавление только от подтверждённого сервером add:
// стартовая загрузка, изменение количества, удаление и ошибка — нет.
describe("CartProvider → шина действий", () => {
  const listener = vi.fn();
  let unsubscribe = () => {};

  beforeEach(() => {
    listener.mockReset();
    mockedGet.mockReset();
    mockedAdd.mockReset();
    mockedUpdate.mockReset();
    mockedRemove.mockReset();
    mockedGet.mockResolvedValue(cartWith(2));
    unsubscribe = subscribeActionSuccess(listener);
  });
  afterEach(() => unsubscribe());

  const renderProbe = () =>
    render(
      <CartProvider>
        <Probe />
      </CartProvider>,
    );

  it("стартовая загрузка корзины событие не издаёт", async () => {
    renderProbe();
    await screen.findByText("count:2");
    expect(listener).not.toHaveBeenCalled();
  });

  it("успешное добавление издаёт событие, ошибка — нет", async () => {
    renderProbe();
    await screen.findByText("count:2");

    mockedAdd.mockResolvedValueOnce(cartWith(3));
    fireEvent.click(screen.getByRole("button", { name: "add" }));
    await screen.findByText("count:3");
    await screen.findByText("ok");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith("cart");

    mockedAdd.mockRejectedValueOnce(new Error("нет связи"));
    fireEvent.click(screen.getByRole("button", { name: "add" }));
    await screen.findByText("ошибка");
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("изменение количества и удаление событие не издают", async () => {
    renderProbe();
    await screen.findByText("count:2");

    mockedUpdate.mockResolvedValueOnce(cartWith(5));
    fireEvent.click(screen.getByRole("button", { name: "update" }));
    await screen.findByText("count:5");
    mockedRemove.mockResolvedValueOnce(cartWith(0));
    fireEvent.click(screen.getByRole("button", { name: "remove" }));
    await waitFor(() => expect(screen.getByText("count:0")).toBeInTheDocument());
    expect(listener).not.toHaveBeenCalled();
  });
});
