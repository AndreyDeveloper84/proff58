// Отзывы (#573). Мутации/«мои» — через BFF (/api/account/reviews, nginx-префикс
// уже в Next); публичный список — GET напрямую в Django (catch-all, без CSRF).
import { ApiError, apiFetch } from "@/lib/api";
import type { MyReview, ProductReviewsPayload } from "@/lib/types";

export type ReviewDraft = {
  order_number: string;
  product_rating: number;
  delivery_rating: number;
  shop_rating: number;
  text?: string;
};

export function createReview(draft: ReviewDraft): Promise<MyReview> {
  return apiFetch<MyReview>("/api/account/reviews", {
    method: "POST",
    body: JSON.stringify(draft),
  });
}

export async function getMyReviews(): Promise<MyReview[] | "disabled"> {
  try {
    const data = await apiFetch<{ results?: MyReview[] }>("/api/account/reviews", {
      method: "GET",
    });
    return data.results ?? [];
  } catch (e) {
    if (e instanceof ApiError && e.code === "reviews_disabled") return "disabled";
    if (e instanceof ApiError) return [];
    throw e;
  }
}

/** Отзыв по конкретному заказу: null — ещё не оставлен, "disabled" — фича выключена. */
export async function getMyReviewForOrder(
  orderNumber: string,
): Promise<MyReview | null | "disabled"> {
  try {
    const data = await apiFetch<{ results?: MyReview[] }>(
      `/api/account/reviews?order=${encodeURIComponent(orderNumber)}`,
      { method: "GET" },
    );
    return data.results?.[0] ?? null;
  } catch (e) {
    if (e instanceof ApiError && e.code === "reviews_disabled") return "disabled";
    if (e instanceof ApiError) return null;
    throw e;
  }
}

/** Клиентская догрузка страницы отзывов товара («Показать ещё»). */
export async function fetchProductReviews(
  slug: string,
  offset: number,
  limit = 10,
): Promise<ProductReviewsPayload | null> {
  try {
    return await apiFetch<ProductReviewsPayload>(
      `/api/reviews/product/${encodeURIComponent(slug)}/?limit=${limit}&offset=${offset}`,
      { method: "GET" },
    );
  } catch {
    return null;
  }
}
