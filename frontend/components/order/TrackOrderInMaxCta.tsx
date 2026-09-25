"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { MaxAuthFlow } from "@/components/account/MaxAuthFlow";
import { getOrderTrackingStatus, startOrderTracking } from "@/lib/auth";

// CTA «Отслеживать заказ в MAX» на странице «Спасибо за заказ» (#520): гость
// подключает уведомления по ОДНОМУ этому заказу без регистрации/входа — не
// путать с полноценным MaxAuthFlow login/link. Сервер сверяет телефон MAX с
// customer_phone заказа; при несовпадении — жёсткий отказ (см. бэкенд #520),
// без раскрытия заказа. Токен гостевого доступа уходит только в тело POST
// /max-track/start (BFF → Django), никогда в MAX/лог.
//
// MaxAuthFlow сам рисует свою кнопку-идентификатор (ctaLabel) — отдельной
// «внешней» кнопки-дубля здесь нет: два одинаковых по смыслу CTA подряд
// потребовали бы от пользователя лишнего клика.
export function TrackOrderInMaxCta({
  orderNumber,
  accessToken,
}: {
  orderNumber: string;
  accessToken: string;
}) {
  const [connected, setConnected] = useState(false);

  if (connected) {
    return (
      <p className="inline-flex items-center gap-1.5 text-sm font-medium text-brand">
        <Check className="h-4 w-4" aria-hidden />
        Отслеживание подключено — обновления придут в MAX
      </p>
    );
  }

  return (
    <div className="max-w-sm">
      <MaxAuthFlow
        ctaLabel="Отслеживать заказ в MAX"
        start={() => startOrderTracking(orderNumber, accessToken)}
        pollStatus={getOrderTrackingStatus}
        onCompleted={() => setConnected(true)}
      />
    </div>
  );
}
