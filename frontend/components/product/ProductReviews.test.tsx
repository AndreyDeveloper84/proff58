import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/reviews", () => ({ fetchProductReviews: vi.fn() }));

import { fetchProductReviews } from "@/lib/reviews";
import { ProductReviews } from "./ProductReviews";

const mockedFetch = fetchProductReviews as unknown as ReturnType<typeof vi.fn>;

function review(overrides: Record<string, unknown> = {}) {
  return {
    author_name: "Иван",
    product_rating: 5,
    text: "Отличный инструмент",
    created_at: "2026-07-21T10:00:00+03:00",
    ...overrides,
  };
}

describe("ProductReviews (#573/#574)", () => {
  beforeEach(() => mockedFetch.mockReset());

  it("пустое состояние приглашает оставить первый отзыв", () => {
    render(
      <ProductReviews
        slug="perforator"
        initial={{ count: 0, results: [], summary: { product_rating_avg: null, count: 0 } }}
      />,
    );
    expect(screen.getByText("Отзывов пока нет")).toBeTruthy();
    expect(screen.getByText(/поделитесь впечатлением первым/)).toBeTruthy();
  });

  it("показывает средний рейтинг и дату в общем формате", () => {
    render(
      <ProductReviews
        slug="perforator"
        initial={{
          count: 1,
          results: [review()],
          summary: { product_rating_avg: 4.8, count: 1 },
        }}
      />,
    );
    expect(screen.getByText("Отзывы (1)")).toBeTruthy();
    expect(screen.getByText("4.8")).toBeTruthy();
    // #574: та же форма даты, что в кабинете (раньше здесь было «21 июля 2026»).
    expect(screen.getByText("21.07.2026")).toBeTruthy();
  });

  // #574: раньше сбой догрузки проглатывался и кнопка молча не срабатывала.
  it("ошибка догрузки видна и предлагает повтор", async () => {
    mockedFetch.mockResolvedValue(null);
    render(
      <ProductReviews
        slug="perforator"
        initial={{
          count: 2,
          results: [review()],
          summary: { product_rating_avg: 5, count: 2 },
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(await screen.findByText(/Не удалось загрузить остальные отзывы/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeTruthy();
  });
});
