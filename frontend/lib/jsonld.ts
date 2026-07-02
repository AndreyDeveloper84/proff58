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
export function serializeJsonLd(data: unknown): string {
  return JSON.stringify(data)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}
