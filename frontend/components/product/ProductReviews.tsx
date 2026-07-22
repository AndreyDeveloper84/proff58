"use client";

import { useState } from "react";
import { Star } from "lucide-react";
import { StarDisplay } from "@/components/reviews/StarRating";
import { formatDate } from "@/lib/format";
import { fetchProductReviews } from "@/lib/reviews";
import type { ProductReviewsPayload, PublicReview } from "@/lib/types";

// Публичные отзывы товара (#573): SSR отдал первую страницу+агрегат,
// «Показать ещё» догружает клиентски. Только approved (гарантирует бэк).
export function ProductReviews({
  slug,
  initial,
}: {
  slug: string;
  initial: ProductReviewsPayload;
}) {
  const [items, setItems] = useState<PublicReview[]>(initial.results);
  const [loading, setLoading] = useState(false);
  const total = initial.count;
  const avg = initial.summary.product_rating_avg;

  const loadMore = async () => {
    setLoading(true);
    const next = await fetchProductReviews(slug, items.length);
    if (next) setItems((prev) => [...prev, ...next.results]);
    setLoading(false);
  };

  return (
    <section className="mt-10">
      <h2 className="mb-4 flex items-center gap-3 font-display text-2xl font-semibold uppercase tracking-wide text-ink">
        Отзывы ({total})
        {avg !== null && total > 0 && (
          <span className="inline-flex items-center gap-1 text-lg normal-case text-ink-2">
            <Star className="h-5 w-5 fill-amber-400 text-amber-400" aria-hidden />
            {avg.toFixed(1)}
          </span>
        )}
      </h2>
      {total === 0 ? (
        <p className="rounded-lg border border-line bg-surface p-6 text-sm text-ink-2">
          Пока нет отзывов. Купите товар — и поделитесь впечатлением первым.
        </p>
      ) : (
        <div className="space-y-4">
          {items.map((review, i) => (
            <article key={i} className="rounded-lg border border-line bg-surface p-4">
              <div className="flex flex-wrap items-center gap-3">
                <StarDisplay value={review.product_rating} />
                <span className="text-sm font-semibold text-ink">{review.author_name}</span>
                <span className="text-xs text-ink-3">{formatDate(review.created_at)}</span>
              </div>
              {review.text && <p className="mt-2 text-sm text-ink-2">{review.text}</p>}
            </article>
          ))}
          {items.length < total && (
            <button
              type="button"
              onClick={loadMore}
              disabled={loading}
              className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink transition hover:border-accent disabled:opacity-50"
            >
              {loading ? "Загружаем…" : "Показать ещё"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
