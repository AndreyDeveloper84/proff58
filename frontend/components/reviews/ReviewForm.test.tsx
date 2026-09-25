import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/reviews", () => ({ createReview: vi.fn() }));

import { ApiError } from "@/lib/api";
import { createReview } from "@/lib/reviews";
import { ReviewForm } from "./ReviewForm";

const mocked = createReview as unknown as ReturnType<typeof vi.fn>;

function pick(label: string, n: number) {
  const group = screen.getByRole("radiogroup", { name: label });
  fireEvent.click(group.querySelectorAll("button")[n - 1]);
}

describe("ReviewForm (#573)", () => {
  beforeEach(() => mocked.mockReset());

  it("сабмит заблокирован без трёх оценок; отправляет выбранные значения", async () => {
    mocked.mockResolvedValue({ id: 1, status: "pending" });
    const onDone = vi.fn();
    render(<ReviewForm orderNumber="П-1" onDone={onDone} onCancel={vi.fn()} />);

    const submit = screen.getByRole("button", { name: /отправить отзыв/i });
    expect(submit).toHaveProperty("disabled", true);

    pick("Товары", 5);
    pick("Доставка", 4);
    expect(submit).toHaveProperty("disabled", true); // ещё нет оценки магазина
    pick("Магазин", 5);
    fireEvent.change(screen.getByLabelText("Текст отзыва"), { target: { value: "Ок" } });
    fireEvent.click(submit);

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(mocked.mock.calls[0][0]).toMatchObject({
      order_number: "П-1",
      product_rating: 5,
      delivery_rating: 4,
      shop_rating: 5,
      text: "Ок",
    });
  });

  it("ошибка бэка показывается человеческим текстом", async () => {
    mocked.mockRejectedValueOnce(new ApiError("Вы уже оставили отзыв по этому заказу.", 409));
    render(<ReviewForm orderNumber="П-1" onDone={vi.fn()} onCancel={vi.fn()} />);
    pick("Товары", 5);
    pick("Доставка", 5);
    pick("Магазин", 5);
    fireEvent.click(screen.getByRole("button", { name: /отправить отзыв/i }));
    await waitFor(() =>
      expect(screen.getByText(/уже оставили отзыв/i)).toBeInTheDocument(),
    );
  });
});
