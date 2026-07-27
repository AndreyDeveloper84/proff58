"use client";

import { useState } from "react";
import { LoaderCircle } from "lucide-react";
import { StarRating } from "@/components/reviews/StarRating";
import { ApiError } from "@/lib/api";
import { createReview } from "@/lib/reviews";
import type { MyReview } from "@/lib/types";

// Форма «Оставить отзыв» (#573): 3 оценки обязательны, текст опционален.
export function ReviewForm({
  orderNumber,
  onDone,
  onCancel,
}: {
  orderNumber: string;
  onDone: (review: MyReview) => void;
  onCancel: () => void;
}) {
  const [productRating, setProductRating] = useState(0);
  const [deliveryRating, setDeliveryRating] = useState(0);
  const [shopRating, setShopRating] = useState(0);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const ready = productRating > 0 && deliveryRating > 0 && shopRating > 0;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ready || saving) return;
    setSaving(true);
    setError("");
    try {
      const review = await createReview({
        order_number: orderNumber,
        product_rating: productRating,
        delivery_rating: deliveryRating,
        shop_rating: shopRating,
        text: text.trim(),
      });
      onDone(review);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Не удалось отправить отзыв");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <StarRating label="Товары" value={productRating} onChange={setProductRating} />
      <StarRating label="Доставка" value={deliveryRating} onChange={setDeliveryRating} />
      <StarRating label="Магазин" value={shopRating} onChange={setShopRating} />
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Расскажите о покупке (необязательно)"
        aria-label="Текст отзыва"
        rows={4}
        maxLength={4000}
        className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none"
      />
      {error && (
        <p role="alert" className="rounded-md border border-danger/10 bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-line px-4 py-2 text-sm text-ink transition hover:border-accent"
        >
          Отмена
        </button>
        <button
          type="submit"
          disabled={!ready || saving}
          className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink disabled:opacity-50"
        >
          {saving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
          {saving ? "Отправляем…" : "Отправить отзыв"}
        </button>
      </div>
    </form>
  );
}
