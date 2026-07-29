// Безопасная сериализация JSON-LD для вставки в <script type="application/ld+json">.
//
// JSON.stringify не экранирует символы, способные разорвать HTML-контекст <script>
// или JS-строку. Значение вроде `</script><script>alert(1)</script>` в названии/
// описании товара (данные из admin/1С/контентных источников — недоверенные) иначе
// закрыло бы тег и выполнило произвольный скрипт (stored XSS, M-01).
//
// Экранируем:
//   <  → <   (защита от закрытия </script> и HTML-инъекций)
//   >  → >
//   &  → &
//   U+2028 / U+2029 — валидные в JSON line separators, но ломают JS-строку.
//
// Результат остаётся валидным JSON: браузерный парсер JSON-LD читает исходные
// символы обратно, а HTML-парсер литерального </script> уже не видит.
// Публичный адрес витрины — тот же источник, что у metadataBase в app/layout.tsx.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://proff58.ru";

/**
 * Абсолютный URL для микроразметки.
 *
 * API отдаёт медиа относительным путём (`/media/…`) — так ссылка не зависит от
 * того, кто спросил: браузер и SSR разрешают её от своего origin. Разметке для
 * поисковиков этого мало: Google требует абсолютные ссылки на изображения
 * товара, поэтому origin достраиваем здесь.
 */
export function absoluteUrl(path: string): string {
  return /^https?:\/\//i.test(path) ? path : new URL(path, SITE_URL).toString();
}

export function serializeJsonLd(data: unknown): string {
  return JSON.stringify(data)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}
