"use client";

import { useState } from "react";
import { Check, Share2 } from "lucide-react";

// Кнопка «Поделиться»: системный Web Share API, фолбэк — копирование ссылки в буфер.
export function ShareButton({ title }: { title: string }) {
  const [copied, setCopied] = useState(false);

  const share = async () => {
    const url = typeof window !== "undefined" ? window.location.href : "";
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ title, url });
      } catch {
        // Пользователь отменил шеринг — это не ошибка.
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Буфер недоступен (нет HTTPS/прав) — молча игнорируем.
    }
  };

  return (
    <button
      type="button"
      onClick={share}
      aria-label="Поделиться"
      className="inline-flex shrink-0 items-center gap-1.5 text-sm text-ink-3 hover:text-accent"
    >
      {copied ? (
        <Check className="h-4 w-4" aria-hidden />
      ) : (
        <Share2 className="h-4 w-4" aria-hidden />
      )}
      {copied ? "Скопировано" : "Поделиться"}
    </button>
  );
}
