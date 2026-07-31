import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  usePathname: () => "/account/reviews",
}));
vi.mock("@/lib/auth", () => ({
  checkAuth: vi.fn(),
  loginHref: (next?: string) => (next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login"),
}));
vi.mock("@/lib/reviews", () => ({
  getMyReviews: vi.fn(),
  // #574: статусы теперь берутся из общего словаря, а не из status_display бэка.
  REVIEW_STATUS_LABEL: {
    pending: "На модерации",
    approved: "Опубликован",
    rejected: "Отклонён",
  },
}));

import { checkAuth } from "@/lib/auth";
import { getMyReviews } from "@/lib/reviews";
import MyReviewsPage from "./page";

const mockedGetMe = checkAuth as unknown as ReturnType<typeof vi.fn>;
const mockedGetMyReviews = getMyReviews as unknown as ReturnType<typeof vi.fn>;

function review(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    order_number: "П-1",
    product_rating: 5,
    delivery_rating: 4,
    shop_rating: 5,
    text: "Отлично",
    status: "pending",
    status_display: "На модерации",
    rejection_reason: "",
    created_at: "2026-07-21T10:00:00+03:00",
    ...overrides,
  };
}

describe("MyReviewsPage (#573)", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetMyReviews.mockReset();
    mockedGetMe.mockResolvedValue({ id: 1, customer_type: "b2c" });
  });

  it("статусы и причина отклонения", async () => {
    mockedGetMyReviews.mockResolvedValue([
      review(),
      review({ id: 2, order_number: "П-2", status: "approved", status_display: "Опубликован" }),
      review({
        id: 3,
        order_number: "П-3",
        status: "rejected",
        status_display: "Отклонён",
        rejection_reason: "Нецензурная лексика",
      }),
    ]);
    render(<MyReviewsPage />);
    expect(await screen.findByText("На модерации")).toBeTruthy();
    expect(screen.getByText("Опубликован")).toBeTruthy();
    expect(screen.getByText("Отклонён")).toBeTruthy();
    expect(screen.getByText(/Нецензурная лексика/)).toBeTruthy();
  });

  it("пустое состояние и off-состояние", async () => {
    mockedGetMyReviews.mockResolvedValue([]);
    const { unmount } = render(<MyReviewsPage />);
    expect(await screen.findByText("Отзывов пока нет")).toBeTruthy();
    unmount();

    mockedGetMyReviews.mockResolvedValue("disabled");
    render(<MyReviewsPage />);
    expect(await screen.findByText(/временно отключён/)).toBeTruthy();
  });

  it("гость уводится на логин", async () => {
    mockedGetMe.mockResolvedValue("anonymous");
    render(<MyReviewsPage />);
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/account/login?next=%2Faccount%2Freviews"));
  });
});
