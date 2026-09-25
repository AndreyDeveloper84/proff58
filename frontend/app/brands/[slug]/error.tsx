"use client";

// Сбой API на странице бренда — это ошибка с «Повторить», а не «товаров бренда нет»:
// пустая выдача и недоступный каталог для покупателя означают разное (UX-07, PERF-01).
import { RouteError } from "@/components/ui/RouteError";

export default function BrandError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} scope="brand listing" title="Не удалось загрузить товары бренда" />;
}
