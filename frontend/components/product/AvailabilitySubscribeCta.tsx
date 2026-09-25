"use client";

import { useEffect, useState } from "react";
import { Bell, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MaxAuthFlow } from "@/components/account/MaxAuthFlow";
import { ApiError } from "@/lib/api";
import { getMe, maxAccountStatus } from "@/lib/auth";
import {
  getAvailabilitySubscriptionStatus,
  subscribeAvailability,
  unsubscribeAvailability,
} from "@/lib/notifications";

// CTA «Сообщить о поступлении» для out-of-stock карточки товара (#519, заменяет
// старый Inquiry-флоу «Уточнить поступление» для этого сценария — #517 даёт
// самообслуживаемую подписку вместо заявки менеджеру). Сервер — источник истины
// по наличию/статусу подписки: клиент только отражает то, что уже вернул бэк.
//
// Состояния: idle → (не авторизован → редирект на логин) →
// (нет MAX → needs-max, инлайн-подключение) → loading → subscribed | error.
type Phase = "checking" | "idle" | "needs-max" | "loading" | "subscribed" | "error";

export function AvailabilitySubscribeCta({ productSlug }: { productSlug: string }) {
  const [phase, setPhase] = useState<Phase>("checking");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      const user = await getMe().catch(() => null);
      if (!user) {
        if (active) setPhase("idle");
        return;
      }
      const status = await getAvailabilitySubscriptionStatus(productSlug).catch(() => null);
      if (!active) return;
      setPhase(status?.status === "active" || status?.status === "queued" ? "subscribed" : "idle");
    })();
    return () => {
      active = false;
    };
  }, [productSlug]);

  async function handleSubscribeClick() {
    setErrorMsg("");
    const user = await getMe().catch(() => null);
    if (!user) {
      window.location.href = `/account/login?next=${encodeURIComponent(`/product/${productSlug}`)}`;
      return;
    }
    const max = await maxAccountStatus().catch(() => ({ linked: false }));
    if (!max.linked) {
      setPhase("needs-max");
      return;
    }
    await doSubscribe();
  }

  async function doSubscribe() {
    setPhase("loading");
    setErrorMsg("");
    try {
      await subscribeAvailability(productSlug);
      setPhase("subscribed");
    } catch (err) {
      setPhase("error");
      setErrorMsg(actionableMessage(err, "subscribe"));
    }
  }

  async function handleCancel() {
    setPhase("loading");
    setErrorMsg("");
    try {
      await unsubscribeAvailability(productSlug);
      setPhase("idle");
    } catch (err) {
      setPhase("error");
      setErrorMsg(actionableMessage(err, "unsubscribe"));
    }
  }

  if (phase === "checking") return null; // избегаем «мигания» кнопки до первого ответа

  if (phase === "subscribed") {
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="inline-flex items-center gap-1.5 font-medium text-brand">
          <Check className="h-4 w-4" aria-hidden />
          Мы сообщим вам в MAX
        </span>
        <button type="button" onClick={handleCancel} className="text-ink-3 underline hover:text-ink">
          Отменить
        </button>
      </div>
    );
  }

  if (phase === "needs-max") {
    return (
      <div className="max-w-sm rounded-md border border-line bg-surface p-3">
        <p className="mb-2 text-sm text-ink-2">Чтобы получить уведомление, подключите MAX:</p>
        <MaxAuthFlow mode="link" ctaLabel="Подключить MAX" onCompleted={doSubscribe} />
        {errorMsg && (
          <p role="alert" className="mt-2 text-xs text-danger">
            {errorMsg}
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      <Button
        variant="outline"
        onClick={handleSubscribeClick}
        disabled={phase === "loading"}
        data-event="subscribe_availability"
        data-product-slug={productSlug}
      >
        {phase === "loading" ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        ) : (
          <Bell className="h-4 w-4" aria-hidden />
        )}
        Сообщить о поступлении
      </Button>
      {errorMsg && (
        <p role="alert" className="mt-1 text-xs text-danger">
          {errorMsg}
        </p>
      )}
    </div>
  );
}

// Actionable-тексты под коды бэка (#517 AC): already_in_stock/max_connection_required
// как понятные фразы, остальное — общий текст с предложением повторить.
function actionableMessage(err: unknown, action: "subscribe" | "unsubscribe"): string {
  if (err instanceof ApiError) {
    if (err.code === "already_in_stock") {
      return "Товар уже в наличии — обновите страницу.";
    }
    if (err.code === "max_connection_required") {
      return "Нужна активная привязка MAX. Подключите её и попробуйте снова.";
    }
    if (err.status === 401 || err.status === 403) {
      return "Сессия истекла. Войдите заново и повторите попытку.";
    }
    return err.message;
  }
  return action === "subscribe"
    ? "Не удалось оформить подписку. Попробуйте ещё раз."
    : "Не удалось отменить подписку. Попробуйте ещё раз.";
}
