// Серверный прокси BFF (#246). Импортируется ТОЛЬКО из route handlers (app/api/**),
// то есть исполняется на сервере Next — секреты и адрес Django браузеру не видны.
//
// Зачем BFF: браузер ходит лишь в same-origin /api/... (Next), а реальные обращения к
// Django идут серверной стороной по INTERNAL_API_BASE_URL. Это снимает CORS/CSRF и не
// «протекает» контрактом Django в браузер. Прокси:
//   1. читает cookie входящего запроса (session) и пробрасывает их в Django;
//   2. для мутаций обеспечивает CSRF: самосогласованный csrftoken (cookie + X-CSRFToken) и
//      Referer, проходящие проверку Django (нужно для ВОШЕДШЕГО пользователя — DRF
//      enforce_csrf срабатывает только на аутентифицированной сессии; гостю CSRF не нужен);
//   3. возвращает тело+статус Django и пробрасывает его Set-Cookie клиенту (session+csrftoken).
import type { NextRequest } from "next/server";

// Адрес Django внутри сети (как в lib/catalog.ts: http://web:8000 в compose). Только server-side.
const INTERNAL_API_BASE_URL = process.env.INTERNAL_API_BASE_URL;

// Server-side заголовок: Django в prod редиректит http→https (SECURE_SSL_REDIRECT); сообщаем
// через SECURE_PROXY_SSL_HEADER, что запрос уже защищён, иначе зациклит редирект (см. adapters).
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;

// Алфавит CSRF-токена Django (CSRF_ALLOWED_CHARS = ascii_letters + digits), длина секрета — 32.
const CSRF_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

type ProxyInit = {
  method: string;
  // Сырое тело запроса (JSON-строка) для POST/PATCH; для GET/DELETE — не передаётся.
  body?: string;
};

// 32-символьный токен из алфавита Django. Токен не обязан быть секретным: cookie и заголовок
// несут одно значение, Django лишь сверяет их между собой (_does_token_match). CSRF-защита
// реальна на границе браузер→Next (same-origin), а Next→Django — доверенный серверный вызов.
function randomCsrfToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let out = "";
  for (const b of bytes) out += CSRF_ALPHABET[b % CSRF_ALPHABET.length];
  return out;
}

// Переиспользуем валидный csrftoken браузера (стабильность), иначе минтим новый.
function csrfTokenFor(request: NextRequest): string {
  const existing = request.cookies.get("csrftoken")?.value;
  return existing && /^[A-Za-z0-9]{32}$|^[A-Za-z0-9]{64}$/.test(existing)
    ? existing
    : randomCsrfToken();
}

// Cookie-заголовок для Django: убираем старый csrftoken и кладём наш (совпадает с X-CSRFToken).
function cookieWithCsrf(cookieHeader: string, token: string): string {
  const parts = cookieHeader
    .split(";")
    .map((p) => p.trim())
    .filter((p) => p && !p.toLowerCase().startsWith("csrftoken="));
  parts.push(`csrftoken=${token}`);
  return parts.join("; ");
}

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
  let cookie = request.headers.get("cookie") ?? "";

  const isMutation = init.method !== "GET" && init.method !== "HEAD";
  if (init.body != null) headers["content-type"] = "application/json";

  // CSRF (только мутации). DRF enforce_csrf срабатывает лишь на аутентифицированной сессии
  // (гостю не нужно, но лишним не будет). Django (cookie-based CSRF) принимает самосогласованную
  // пару: одинаковый токен в cookie csrftoken и заголовке X-CSRFToken. На HTTPS Django ещё
  // проверяет Referer — шлём его на хост самого Django (совпадает с request.get_host()).
  let csrftoken: string | null = null;
  if (isMutation) {
    csrftoken = csrfTokenFor(request);
    cookie = cookieWithCsrf(cookie, csrftoken);
    headers["X-CSRFToken"] = csrftoken;
    headers["referer"] = `https://${new URL(root).host}/`;
  }
  if (cookie) headers["cookie"] = cookie;

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
  // Закрепляем csrftoken у браузера, чтобы следующие мутации переиспользовали тот же токен
  // (csrftoken не httpOnly по дизайну Django; не Secure — чтобы работал и на http-dev).
  if (csrftoken) {
    responseHeaders.append(
      "set-cookie",
      `csrftoken=${csrftoken}; Path=/; SameSite=Lax`,
    );
  }

  // 204/205/304 — null-body-статусы: Response запрещает передавать им тело (даже
  // пустое ArrayBuffer), иначе конструктор бросает TypeError.
  const NULL_BODY_STATUSES = new Set([101, 103, 204, 205, 304]);
  const body = NULL_BODY_STATUSES.has(upstream.status) ? null : await upstream.arrayBuffer();
  return new Response(body, { status: upstream.status, headers: responseHeaders });
}
