// Серверная проверка доступа в личный кабинет (исполняется только на сервере Next).
//
// Зачем нужна, если есть proxy.ts. Proxy судит по cookie — то есть по косвенному
// признаку: он не знает, жива ли сессия на самом деле, и намеренно оптимистичен,
// потому что стоит на пути каждого запроса кабинета. Из-за этого гость с cookie
// (её выдаёт и анонимному посетителю, например гостевой корзине) проходил внутрь
// и получал готовую разметку кабинета — а браузер уже потом уводил его на вход.
// Здесь проверка настоящая: спрашиваем у Django «кто это», и решение принимается
// ДО отдачи HTML, поэтому чужой кабинет не мелькает.
//
// Цена — один серверный запрос на переход внутри кабинета; на остальной сайт это
// не распространяется.

const INTERNAL_API_BASE_URL = process.env.INTERNAL_API_BASE_URL;

// Django в prod редиректит http→https (SECURE_SSL_REDIRECT); сообщаем через
// SECURE_PROXY_SSL_HEADER, что запрос уже защищён, — тот же приём, что в lib/bff.ts.
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;

/**
 * Итог проверки:
 * - `authenticated` — пускаем;
 * - `anonymous` — Django сказал «не вошёл» (401/403), уводим на форму входа;
 * - `unavailable` — связь/сервер/конфиг подвели. НЕ «не вошёл»: выгонять человека
 *   с живой сессией из-за чужой ошибки нельзя, страница сама покажет, что сервис
 *   временно недоступен.
 */
export type ServerAuthState = "authenticated" | "anonymous" | "unavailable";

/**
 * Спросить Django, вошёл ли владелец этих cookie.
 *
 * @param cookieHeader заголовок Cookie входящего запроса (браузер → Next).
 */
export async function checkServerAuth(cookieHeader: string): Promise<ServerAuthState> {
  if (!INTERNAL_API_BASE_URL) return "unavailable";

  // Без cookie в Django можно не ходить — вошедших без них не бывает.
  if (!cookieHeader) return "anonymous";

  const root = INTERNAL_API_BASE_URL.replace(/\/$/, "");
  let response: Response;
  try {
    response = await fetch(`${root}/api/account/me/`, {
      method: "GET",
      headers: { ...SSR_HEADERS, cookie: cookieHeader },
      cache: "no-store",
      // Редиректы не наши: 30x от Django здесь означает «что-то не так с адресом»,
      // а не ответ про пользователя.
      redirect: "manual",
    });
  } catch {
    return "unavailable";
  }

  if (response.ok) return "authenticated";
  if (response.status === 401 || response.status === 403) return "anonymous";
  return "unavailable";
}
