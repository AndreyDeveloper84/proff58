"use client";

// Сбой поиска — это ошибка с «Повторить», а не «По запросу ничего не найдено»:
// покупатель, увидев пустую выдачу при упавшем API, решает, что товара нет (PERF-01).
import { RouteError } from "@/components/ui/RouteError";

export default function SearchError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <RouteError
      {...props}
      scope="search"
      title="Поиск сейчас не отвечает"
      text="Это сбой на нашей стороне, а не отсутствие товара. Попробуйте ещё раз."
    />
  );
}
