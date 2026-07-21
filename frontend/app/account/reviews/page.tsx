"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Star } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { StarDisplay } from "@/components/reviews/StarRating";
import { getMe } from "@/lib/auth";
import { getMyReviews } from "@/lib/reviews";
import type { MyReview, ReviewStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_BADGE: Record<ReviewStatus, string> = {
  pending: "bg-amber-50 text-amber-700",
  approved: "bg-accent/10 text-accent",
  rejected: "bg-red-50 text-danger",
};

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export default function MyReviewsPage() {
  const router = useRouter();
  const [items, setItems] = useState<MyReview[]>([]);
  const [disabled, setDisabled] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getMe()
      .then(async (user) => {
        if (!user) {
          router.push("/account/login");
          return;
        }
        const data = await getMyReviews();
        if (!active) return;
        if (data === "disabled") setDisabled(true);
        else setItems(data);
        setLoading(false);
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (loading) {
    return (
      <AccountShell title="Отзывы">
        <div className="space-y-4" aria-label="Загрузка отзывов">
          <div className="h-36 animate-pulse rounded-lg border border-line bg-surface" />
          <div className="h-36 animate-pulse rounded-lg border border-line bg-surface" />
        </div>
      </AccountShell>
    );
  }

  return (
    <AccountShell title="Отзывы">
      {disabled ? (
        <div className="rounded-lg border border-line bg-surface p-10 text-center text-sm text-ink-2">
          Раздел отзывов временно отключён.
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-line bg-surface p-10 text-center">
          <Star className="mx-auto h-10 w-10 text-ink-3" aria-hidden />
          <h2 className="mt-3 font-display text-lg font-semibold text-ink">Отзывов пока нет</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-ink-2">
            После получения заказа на его странице появится кнопка «Оставить отзыв».
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((review) => (
            <article key={review.id} className="rounded-lg border border-line bg-surface p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link
                  href={`/account/orders/${encodeURIComponent(review.order_number)}`}
                  className="font-display text-lg font-semibold text-ink underline-offset-2 hover:underline"
                >
                  Заказ {review.order_number}
                </Link>
                <span
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-semibold",
                    STATUS_BADGE[review.status],
                  )}
                >
                  {review.status_display}
                </span>
              </div>
              <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-ink-3">Товары</dt>
                  <dd><StarDisplay value={review.product_rating} /></dd>
                </div>
                <div>
                  <dt className="text-ink-3">Доставка</dt>
                  <dd><StarDisplay value={review.delivery_rating} /></dd>
                </div>
                <div>
                  <dt className="text-ink-3">Магазин</dt>
                  <dd><StarDisplay value={review.shop_rating} /></dd>
                </div>
              </dl>
              {review.text && <p className="mt-3 text-sm text-ink-2">{review.text}</p>}
              {review.status === "rejected" && review.rejection_reason && (
                <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  Причина отклонения: {review.rejection_reason}
                </p>
              )}
              <p className="mt-2 text-xs text-ink-3">{formatDate(review.created_at)}</p>
            </article>
          ))}
        </div>
      )}
    </AccountShell>
  );
}
