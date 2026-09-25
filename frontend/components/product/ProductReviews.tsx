"use client";

import { useState } from "react";
import { Star } from "lucide-react";
import { StarDisplay } from "@/components/reviews/StarRating";
import { EmptyState } from "@/components/ui/states";
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
  // #574: сбой догрузки раньше проглатывался (fetchProductReviews → null), и
  // кнопка «Показать ещё» просто ничего не делала — выглядело как поломка.
  const [loadError, setLoadError] = useState(false);
  const total = initial.count;
  const avg = initial.summary.product_rating_avg;

  const loadMore = async () => {
    setLoading(true);
    setLoadError(false);
    const next = await fetchProductReviews(slug, items.length);
    if (next) setItems((prev) => [...prev, ...next.results]);
    else setLoadError(true);
    setLoading(false);
  };

  return (
    <section
      id="reviews"
      className="mt-8 scroll-mt-24 rounded-lg border border-line bg-surface p-4 sm:p-5"
    >
      <h2 className="mb-4 flex flex-wrap items-center gap-3 font-display text-xl font-semibold text-ink">
        Отзывы ({total})
        {avg !== null && total > 0 && (
          <span className="inline-flex items-center gap-1 text-lg normal-case text-ink-2">
            <Star className="h-5 w-5 fill-current text-rating" aria-hidden />
            {avg.toFixed(1)}
          </span>
        )}
      </h2>
      {total === 0 ? (
        <EmptyState
          icon={<Star className="h-10 w-10" aria-hidden />}
          title="Отзывов пока нет"
          description="Купите товар — и поделитесь впечатлением первым."
          className="rounded-lg border border-line bg-raised"
        />
      ) : (
        <div className="space-y-4">
          {/* Список только дополняется (offset-пагинация, порядок не меняется),
              поэтому индекс — стабильный ключ; id отзыва бэк не отдаёт. */}
          {items.map((review, i) => (
            <article key={i} className="rounded-lg border border-line bg-raised p-4">
              <div className="flex flex-wrap items-center gap-3">
                <StarDisplay value={review.product_rating} />
                <span className="text-sm font-semibold text-ink">{review.author_name}</span>
                <span className="text-xs text-ink-3">{formatDate(review.created_at)}</span>
              </div>
              {review.text && <p className="mt-2 text-sm text-ink-2">{review.text}</p>}
            </article>
          ))}
          {loadError && (
            <p role="alert" className="text-sm text-danger">
              Не удалось загрузить остальные отзывы. Попробуйте ещё раз.
            </p>
          )}
          {items.length < total && (
            <button
              type="button"
              onClick={loadMore}
              disabled={loading}
              className="h-11 rounded-md border border-line px-4 text-sm font-semibold text-ink transition hover:border-accent disabled:opacity-50 sm:h-10"
            >
              {loading ? "Загружаем…" : loadError ? "Повторить" : "Показать ещё"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
