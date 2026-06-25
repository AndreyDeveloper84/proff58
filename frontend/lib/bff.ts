// Серверный прокси BFF (#246). Импортируется ТОЛЬКО из route handlers (app/api/**),
// то есть исполняется на сервере Next — секреты и адрес Django браузеру не видны.
//
// Зачем BFF: браузер ходит лишь в same-origin /api/... (Next), а реальные обращения к
// Django идут серверной стороной по INTERNAL_API_BASE_URL. Это снимает CORS/CSRF и не
// «протекает» контрактом Django в браузер. Прокси:
//   1. читает cookie входящего запроса (session) и пробрасывает их в Django;
//   2. для мутаций добавляет X-CSRFToken из cookie csrftoken (если есть);
//   3. возвращает тело+статус Django и пробрасывает его Set-Cookie клиенту (session).
import type { NextRequest } from "next/server";

// Адрес Django внутри сети (как в lib/catalog.ts: http://web:8000 в compose). Только server-side.
const INTERNAL_API_BASE_URL = process.env.INTERNAL_API_BASE_URL;

// Server-side заголовок: Django в prod редиректит http→https (SECURE_SSL_REDIRECT); сообщаем
// через SECURE_PROXY_SSL_HEADER, что запрос уже защищён, иначе зациклит редирект (см. adapters).
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;

type ProxyInit = {
  method: string;
  // Сырое тело запроса (JSON-строка) для POST/PATCH; для GET/DELETE — не передаётся.
  body?: string;
};

/**
 * Проксировать запрос браузера в Django, сохраняя сессию.
 *
 * @param request входящий запрос к route handler (нужен для cookie заголовка)
 * @param path    путь Django, начиная со слэша (напр. "/api/cart/")
 */
export async function proxyToDjango(
  request: NextRequest,
  path: string,
  init: ProxyInit,
): Promise<Response> {
  if (!INTERNAL_API_BASE_URL) {
    // Конфиг не задан — внятная 502, а не «тихий» бросок исключения наружу.
    return Response.json(
      { detail: "Сервис временно недоступен." },
      { status: 502 },
    );
  }
  const root = INTERNAL_API_BASE_URL.replace(/\/$/, "");

  const headers: Record<string, string> = { ...SSR_HEADERS };
  const cookie = request.headers.get("cookie");
  if (cookie) headers["cookie"] = cookie;

  const isMutation = init.method !== "GET" && init.method !== "HEAD";
  if (init.body != null) headers["content-type"] = "application/json";

  // CSRF: DRF SessionAuthentication требует CSRF только для аутентифицированных по сессии;
  // для анонима (гостевая корзина) enforce_csrf не срабатывает. На случай вошедшего
  // пользователя пробрасываем токен из cookie csrftoken в заголовок (best-effort).
  if (isMutation) {
    const csrftoken = request.cookies.get("csrftoken")?.value;
    if (csrftoken) headers["X-CSRFToken"] = csrftoken;
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${root}${path}`, {
      method: init.method,
      headers,
      body: init.body,
      cache: "no-store",
      // Не следуем редиректам (потеряли бы Set-Cookie и метод) — отдаём как есть.
      redirect: "manual",
    });
  } catch {
    return Response.json(
      { detail: "Сервис временно недоступен." },
      { status: 502 },
    );
  }

  // Отдаём клиенту только нужное: тело, статус, content-type и Set-Cookie (session).
  // Прочие заголовки Django наружу не транслируем (не «протекаем» апстримом).
  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("content-type", contentType);
  for (const setCookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", setCookie);
  }

  const body = await upstream.arrayBuffer();
  return new Response(body, { status: upstream.status, headers: responseHeaders });
}
