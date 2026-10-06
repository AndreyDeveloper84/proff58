"use client";

import { openConsentSettings } from "@/lib/cookie-consent";
import { cn } from "@/lib/utils";

// «Настройки cookie» — в подвале и на странице политики. Подвал и страница —
// серверные компоненты, а открыть баннер можно только из браузера, поэтому
// кнопка вынесена в отдельный клиентский компонент (DRF-2796: изменить или
// отозвать согласие можно в любой момент).
export function CookieSettingsButton({
  className,
  children = "Настройки cookie",
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={openConsentSettings}
      className={cn("text-left hover:text-accent hover:underline", className)}
    >
      {children}
    </button>
  );
}
