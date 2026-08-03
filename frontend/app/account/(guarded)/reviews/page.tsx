"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Star } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { StarDisplay } from "@/components/reviews/StarRating";
import { checkAuth, loginHref } from "@/lib/auth";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { formatDate } from "@/lib/format";
import { REVIEW_STATUS_LABEL, getMyReviews } from "@/lib/reviews";
import type { MyReview, ReviewStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_BADGE: Record<ReviewStatus, string> = {
  pending: "bg-amber-50 text-amber-700",
  approved: "bg-accent/10 text-accent",
  rejected: "bg-red-50 text-danger",
};

export default function MyReviewsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [items, setItems] = useState<MyReview[]>([]);
  const [disabled, setDisabled] = useState(false);
  // #574: сбой загрузки отличаем от «отзывов пока нет».
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    checkAuth()
      .then(async (user) => {
        if (!active) return;
        if (user === "anonymous") {
          router.replace(loginHref(pathname));
          return;
        }
        if (user === "error") {
          setFailed(true);
          setLoading(false);
          return;
        }
        const data = await getMyReviews();
        if (!active) return;
        if (data === "disabled") setDisabled(true);
        else if (data === "error") setFailed(true);
        else setItems(data);
        setLoading(false);
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [router, pathname]);

  if (loading) {
    return (
      <AccountShell title="Отзывы">
        <LoadingState label="Загружаем отзывы…" />
      </AccountShell>
    );
  }

  return (
    <AccountShell title="Отзывы">
      {disabled ? (
        <EmptyState
          icon={<Star className="h-10 w-10" aria-hidden />}
          title="Раздел отзывов временно отключён"
          description="Загляните позже — мы вернём его, как только закончим настройку."
        />
      ) : failed ? (
        <ErrorState
          title="Не удалось загрузить отзывы"
          description="Проверьте соединение и обновите страницу."
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Star className="h-10 w-10" aria-hidden />}
          title="Отзывов пока нет"
          description="После получения заказа на его странице появится кнопка «Оставить отзыв»."
          action={
            <Link
              href="/account/orders"
              className="inline-flex h-11 items-center rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink"
            >
              К моим заказам
            </Link>
          }
        />
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
                  {REVIEW_STATUS_LABEL[review.status]}
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
