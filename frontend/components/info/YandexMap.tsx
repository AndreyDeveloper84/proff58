import { Route } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { resolveStorefront, yandexMapWidgetUrl, yandexRouteUrl } from "@/lib/site";
import { cn } from "@/lib/utils";

// Карта проезда на инфо-страницах. Виджет Яндекса во фрейме, а не картинка:
// картинку нельзя приблизить, она устаревает при смене адреса и не умеет
// строить маршрут.
//
// Точка — по координатам магазина (STORE_MAP в lib/site.ts), а не поиском по
// адресу: поиск `text=` открывал карту без метки, и магазин на ней приходилось
// угадывать. Там же заменяется URL на карту из Яндекс Конструктора.
//
// Фрейм разрешён в CSP отдельной директивой `frame-src https://*.yandex.ru`
// (docker/nginx/default.conf). Без неё действует `default-src 'self'`, и браузер
// режет виджет молча: пустое место вместо карты.

export function YandexMap({
  address,
  className,
}: {
  /** Подпись фрейма для скринридера. По умолчанию — адрес магазина из настроек. */
  address?: string;
  className?: string;
}) {
  const label = address?.trim() || resolveStorefront().address;

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div
        className={cn(
          "relative min-h-64 flex-1 overflow-hidden rounded-xl border border-line bg-canvas",
          // Высота задана пропорцией, а не содержимым: у фрейма нет своей высоты,
          // и без неё блок схлопнется в ноль, а после загрузки дёрнет вёрстку.
          "aspect-[4/3] sm:aspect-[16/10]",
        )}
      >
        <iframe
          src={yandexMapWidgetUrl()}
          title={`Карта: ${label}`}
          className="absolute inset-0 h-full w-full border-0"
          loading="lazy"
          // Виджету не нужны ни камера, ни микрофон; геолокацию он спросит сам,
          // если человек нажмёт «я здесь» — по умолчанию не разрешаем.
          allow=""
          referrerPolicy="strict-origin-when-cross-origin"
        />
      </div>
      {/* Под картой, а не поверх: в углах виджета копирайт и условия Яндекса,
          закрывать их нельзя. */}
      <a
        href={yandexRouteUrl()}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(buttonVariants({ variant: "outline", size: "lg" }), "self-start")}
      >
        <Route aria-hidden className="size-4" />
        Открыть маршрут в Яндекс Картах
      </a>
    </div>
  );
}
