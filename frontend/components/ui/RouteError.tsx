"use client";

// Общая граница ошибок листинговых страниц (каталог, поиск, бренд): внятное
// сообщение и «Повторить» вместо вечного скелетона или ложного «ничего не найдено».
//
// Почему не просто reset(): страницы — серверные компоненты, и reset лишь
// перерисовывает сегмент из того же сломанного ответа сервера, новых данных он
// не запрашивает. Кнопка выглядела рабочей, но ничего не делала — например, пока
// бэкенд поднимался после деплоя. router.refresh() заново идёт на сервер, reset()
// снимает состояние ошибки; вместе внутри одной transition — иначе сброс успеет
// отрисовать старую ошибку раньше, чем придёт свежий ответ.
import { startTransition, useEffect } from "react";
import { useRouter } from "next/navigation";
import { RotateCcw } from "lucide-react";

export function RouteError({
  error,
  reset,
  scope,
  title = "Не удалось загрузить товары",
  text = "Каталог не ответил вовремя или вернул ошибку. Попробуйте ещё раз.",
}: {
  error: Error & { digest?: string };
  reset: () => void;
  /** Метка для консоли: по ней понятно, какой сегмент упал. */
  scope: string;
  title?: string;
  text?: string;
}) {
  const router = useRouter();

  useEffect(() => {
    console.error(`${scope} error:`, error);
  }, [error, scope]);

  const retry = () => {
    startTransition(() => {
      router.refresh();
      reset();
    });
  };

  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <h1 className="text-lg font-semibold text-ink">{title}</h1>
      <p className="mt-2 text-sm text-ink-2">{text}</p>
      <button
        type="button"
        onClick={retry}
        className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink transition hover:brightness-95"
      >
        <RotateCcw className="h-4 w-4" aria-hidden />
        Повторить
      </button>
    </div>
  );
}
