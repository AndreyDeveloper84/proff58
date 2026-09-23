"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { showManualCopy, showToast } from "@/lib/toast";

const MESSAGES = {
  phone: {
    ok: "Номер скопирован в буфер обмена",
    hint: "Скопировать номер телефона",
    manual: "Не удалось скопировать автоматически. Номер выделен — скопируйте его вручную.",
  },
  address: {
    ok: "Адрес скопирован в буфер обмена",
    hint: "Скопировать адрес",
    manual: "Не удалось скопировать автоматически. Адрес выделен — скопируйте его вручную.",
  },
} as const;

// Запасной путь для страниц без Clipboard API (http, старый WebView): временное
// поле + execCommand. Возвращает false, если и он не сработал.
function legacyCopy(text: string): boolean {
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Запрет или потеря фокуса — пробуем запасной путь ниже.
  }
  return legacyCopy(text);
}

/**
 * Контакт, который копируется по нажатию (UX-03).
 *
 * `value` — что именно уходит в буфер: отображаемый номер без `tel:` или ПОЛНЫЙ адрес,
 * даже когда на экране стоит короткая подпись магазина (`children`). Уведомление об
 * успехе показывается только после реального копирования; если буфер недоступен —
 * текст выводится выделенным, чтобы его можно было скопировать руками.
 *
 * Это кнопка, а не ссылка: звонок вынесен в отдельное явно подписанное действие
 * «Позвонить» (`CallLink`), потому что назначение прежней tel-ссылки изменилось.
 */
export function CopyContact({
  kind,
  value,
  children,
  className,
}: {
  kind: keyof typeof MESSAGES;
  value: string;
  children?: ReactNode;
  className?: string;
}) {
  const text = MESSAGES[kind];
  const onClick = async () => {
    if (await copyText(value)) showToast(text.ok);
    else showManualCopy(text.manual, value);
  };
  return (
    <button
      type="button"
      onClick={onClick}
      title={text.hint}
      aria-label={`${text.hint}: ${value}`}
      className={cn("cursor-copy text-left transition hover:text-accent", className)}
    >
      {children ?? value}
    </button>
  );
}

/** Отдельное действие звонка рядом с копируемым номером. */
export function CallLink({ href, className }: { href: string; className?: string }) {
  return (
    <a href={href} className={cn("font-medium text-accent hover:underline", className)}>
      Позвонить
    </a>
  );
}
