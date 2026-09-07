import { resolveStorefront } from "@/lib/site";
import { cn } from "@/lib/utils";

// Карта проезда на инфо-страницах. Виджет Яндекса во фрейме, а не картинка:
// картинку нельзя приблизить, она устаревает при смене адреса и не умеет
// строить маршрут.
//
// Ищем по адресу (`text=`), а не по координатам: адрес приходит из настроек
// витрины, и при переезде магазина карта переезжает сама. Координаты пришлось
// бы править в коде — то есть забыть.
//
// Фрейм разрешён в CSP отдельной директивой `frame-src https://*.yandex.ru`
// (docker/nginx/default.conf). Без неё действует `default-src 'self'`, и браузер
// режет виджет молча: пустое место вместо карты.

const WIDGET_ORIGIN = "https://yandex.ru/map-widget/v1/";
const DEFAULT_ZOOM = 16;

export function YandexMap({
  address,
  zoom = DEFAULT_ZOOM,
  className,
}: {
  /** Адрес поиска. По умолчанию — адрес магазина из настроек витрины. */
  address?: string;
  zoom?: number;
  className?: string;
}) {
  const storefront = resolveStorefront();
  const query = address?.trim() || storefront.address;

  // Пустой адрес в настройках дал бы карту мира — показывать её незачем.
  if (!query) return null;

  const src = `${WIDGET_ORIGIN}?${new URLSearchParams({
    text: query,
    z: String(zoom),
  })}`;

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border border-line bg-canvas",
        // Высота задана пропорцией, а не содержимым: у фрейма нет своей высоты,
        // и без неё блок схлопнется в ноль, а после загрузки дёрнет вёрстку.
        "aspect-[4/3] sm:aspect-[16/10]",
        className,
      )}
    >
      <iframe
        src={src}
        title={`Карта: ${query}`}
        className="absolute inset-0 h-full w-full border-0"
        loading="lazy"
        // Виджету не нужны ни камера, ни микрофон; геолокацию он спросит сам,
        // если человек нажмёт «я здесь» — по умолчанию не разрешаем.
        allow=""
        referrerPolicy="strict-origin-when-cross-origin"
      />
    </div>
  );
}
