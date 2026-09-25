"use client";

// Граница ошибок сегмента каталога (§11). Логика «Повторить» — общая, см. RouteError.
import { RouteError } from "@/components/ui/RouteError";

export default function CatalogError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <RouteError
      {...props}
      scope="catalog listing"
      text="Что-то пошло не так при загрузке каталога. Попробуйте ещё раз."
    />
  );
}
