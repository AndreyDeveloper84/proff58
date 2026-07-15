"use client";

// Граница ошибок сегмента каталога (§11): не бесконечный спиннер, а внятное
// сообщение + «Повторить» (reset перезапускает рендер сегмента). Логируем в консоль.
import { useEffect } from "react";
import { RotateCcw } from "lucide-react";

export default function CatalogError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("catalog listing error:", error);
  }, [error]);

  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <h1 className="text-lg font-semibold text-ink">Не удалось загрузить товары</h1>
      <p className="mt-2 text-sm text-ink-2">
        Что-то пошло не так при загрузке каталога. Попробуйте ещё раз.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink transition hover:brightness-95"
      >
        <RotateCcw className="h-4 w-4" aria-hidden />
        Повторить
      </button>
    </div>
  );
}
