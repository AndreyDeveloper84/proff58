// Заголовки server-side запросов Next → Django (SSR, route handlers публичных страниц).
//
// X-Forwarded-Proto: внутренние запросы идут по http внутри Docker, а Django в prod
// редиректит http→https (SECURE_SSL_REDIRECT). Заголовок сообщает Django через
// SECURE_PROXY_SSL_HEADER, что запрос защищён → без редиректа.
//
// X-SSR-Token (PF-SH-RELEASE-01): SSR ходит в Django напрямую, без X-Forwarded-For,
// поэтому для DRF все посетители сайта — один IP контейнера фронта, и общий анонимный
// лимит отдавал 429 → карточка 500 при обходе краулером. Секрет из окружения
// (SSR_INTERNAL_TOKEN, общий с web) снимает с SSR анонимный лимит. Читается при каждом
// вызове: переменная приходит в рантайме контейнера, а не на этапе build.
//
// ТОЛЬКО server-side! Из браузера не слать; BFF пользовательских действий этот
// заголовок не использует — там лимит считается по IP посетителя (X-Real-IP).
export function ssrHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "X-Forwarded-Proto": "https" };
  const token = process.env.SSR_INTERNAL_TOKEN;
  if (token) headers["X-SSR-Token"] = token;
  return headers;
}
