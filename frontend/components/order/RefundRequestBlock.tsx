"use client";

import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { AccountDialog } from "@/components/account/AccountDialog";
import { formatDate, formatDateTime, formatPrice } from "@/lib/format";
import { getRefundState, requestRefund, type RefundState } from "@/lib/refunds";
import { cn } from "@/lib/utils";

const STATUS_CLASS: Record<string, string> = {
  pending: "bg-raised text-ink-2",
  processing: "bg-raised text-ink-2",
  refunded: "bg-accent/15 text-accent",
  rejected: "bg-danger/10 text-danger",
};

/**
 * Возврат денег за оплаченный онлайн заказ: кнопка заявки и история решений.
 *
 * Деньги возвращает менеджер — покупатель только подаёт заявку. Можно ли её
 * подать, решает сервер; блок не показывается вовсе, если сказать нечего
 * (заказ оплачивается при получении и заявок по нему не было).
 */
export function RefundRequestBlock({
  orderNumber,
  currency,
  onChanged,
}: {
  orderNumber: string;
  currency: string;
  /** Заявка подана — странице стоит перечитать заказ (статус оплаты). */
  onChanged?: () => void;
}) {
  const [state, setState] = useState<RefundState | null>(null);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getRefundState(orderNumber)
      .then((data) => {
        if (active) setState(data);
      })
      // Сбой блока возврата не должен ломать карточку заказа — просто не рисуем его.
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [orderNumber]);

  if (!state) return null;
  const latest = state.requests[0];
  if (!state.can_request && !state.block_reason && !latest) return null;

  const submit = async () => {
    if (!reason) {
      setError("Выберите причину возврата.");
      return;
    }
    if (reason === "other" && !comment.trim()) {
      setError("Опишите, пожалуйста, причину возврата.");
      return;
    }
    setSending(true);
    setError("");
    try {
      setState(await requestRefund(orderNumber, reason, comment.trim()));
      setOpen(false);
      setReason("");
      setComment("");
      onChanged?.();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не удалось отправить заявку. Попробуйте ещё раз.",
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <RotateCcw className="h-5 w-5 text-accent" aria-hidden />
        <h2 className="text-sm font-semibold text-ink">Возврат денег</h2>
      </div>

      {latest && (
        <div className="mt-3 rounded-md border border-line px-3 py-2.5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-md px-2 py-0.5 text-xs font-semibold",
                STATUS_CLASS[latest.status] ?? STATUS_CLASS.pending,
              )}
            >
              {latest.status_label}
            </span>
            <span className="text-xs text-ink-3">
              заявка от {formatDateTime(latest.created_at)} ·{" "}
              {latest.reason_label}
            </span>
          </div>
          {latest.status === "refunded" && latest.amount && (
            <p className="mt-2 text-ink-2">
              Вернули {formatPrice(Number(latest.amount), currency)}. Деньги
              придут на карту, с которой оплачивали, обычно в течение 1–10
              рабочих дней — срок зависит от банка.
            </p>
          )}
          {(latest.status === "pending" || latest.status === "processing") && (
            <p className="mt-2 text-ink-2">
              Менеджер рассмотрит заявку и свяжется с вами. Если товар уже у
              вас, его нужно будет вернуть в магазин.
            </p>
          )}
          {latest.status === "rejected" && latest.decision_comment && (
            <p className="mt-2 text-ink-2">
              Ответ магазина: {latest.decision_comment}
            </p>
          )}
        </div>
      )}

      {state.can_request ? (
        <div className="mt-3">
          <p className="text-sm text-ink-2">
            Если заказ не нужен или с товаром что-то не так, оставьте заявку —
            менеджер её рассмотрит и вернёт деньги на карту.
            {state.deadline && (
              <> Заявку можно подать до {formatDate(state.deadline)}.</>
            )}
          </p>
          <button
            type="button"
            onClick={() => {
              setError("");
              setOpen(true);
            }}
            className="mt-3 inline-flex h-11 items-center rounded-md border border-line px-4 text-sm font-semibold text-ink transition hover:bg-raised sm:h-10"
          >
            Вернуть деньги
          </button>
        </div>
      ) : (
        state.block_reason &&
        !(
          latest &&
          (latest.status === "pending" || latest.status === "processing")
        ) && <p className="mt-3 text-sm text-ink-3">{state.block_reason}</p>
      )}

      <AccountDialog
        title="Заявка на возврат денег"
        description="Менеджер рассмотрит заявку и свяжется с вами. Деньги вернутся на карту, с которой оплачивали заказ."
        open={open}
        onClose={() => setOpen(false)}
      >
        <div className="space-y-4">
          <fieldset>
            <legend className="text-sm font-medium text-ink">Причина</legend>
            <div className="mt-2 space-y-1.5">
              {state.reasons.map((item) => (
                <label
                  key={item.value}
                  className="flex items-center gap-2 text-sm text-ink-2"
                >
                  <input
                    type="radio"
                    name="refund-reason"
                    value={item.value}
                    checked={reason === item.value}
                    onChange={() => setReason(item.value)}
                    className="h-4 w-4 accent-accent"
                  />
                  {item.label}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="block text-sm font-medium text-ink">
            Комментарий{reason === "other" ? "" : " (необязательно)"}
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              maxLength={1000}
              rows={3}
              className="mt-1.5 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm font-normal text-ink"
              placeholder="Что случилось с заказом"
            />
          </label>
          {error && (
            <p
              role="alert"
              className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {error}
            </p>
          )}
          <div className="flex flex-col gap-2 sm:flex-row-reverse">
            <button
              type="button"
              onClick={submit}
              disabled={sending}
              className="inline-flex h-11 items-center justify-center rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink transition disabled:opacity-60"
            >
              {sending ? "Отправляем…" : "Отправить заявку"}
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={sending}
              className="inline-flex h-11 items-center justify-center rounded-md border border-line px-5 text-sm font-medium text-ink transition hover:bg-raised disabled:opacity-60"
            >
              Не нужно
            </button>
          </div>
        </div>
      </AccountDialog>
    </section>
  );
}
