// Клиентский fetch-хелпер для обращений браузера в same-origin BFF (/api/**, #246).
// Только клиентская сторона: cookie сессии отправляются автоматически (same-origin).
// Серверные обращения к Django живут отдельно (lib/adapters.ts, lib/bff.ts) — не дублируем.

// Ошибка обращения к BFF: несёт HTTP-статус, человекочитаемый detail из ответа
// Django и (если бэк его отдал) машиночитаемый code — напр. #517/#519:
// {"detail": "...", "code": "already_in_stock"} — для actionable-веток на фронте
// вместо разбора текста сообщения.
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Машиночитаемый code из тела ошибки, если бэк его прислал (см. ApiError.code). */
export function extractErrorCode(body: unknown): string | undefined {
  if (body && typeof body === "object" && typeof (body as Record<string, unknown>).code === "string") {
    return (body as Record<string, unknown>).code as string;
  }
  return undefined;
}

/**
 * Запасной текст, когда бэк не прислал ни `detail`, ни пофайлдовых ошибок (#574).
 * Раньше здесь возвращалось «Ошибка 500.» — этот текст попадал прямо в баннер
 * checkout и кабинета, то есть пользователь видел HTTP-код вместо действия.
 */
function fallbackErrorMessage(status: number): string {
  if (status === 401 || status === 403) return "Сессия истекла. Войдите заново и повторите.";
  if (status === 404) return "Данные не найдены — возможно, страница устарела. Обновите её.";
  if (status === 429) return "Слишком много попыток. Подождите минуту и повторите.";
  if (status >= 500) return "Сервис временно недоступен. Попробуйте повторить через минуту.";
  return "Не удалось выполнить действие. Попробуйте ещё раз.";
}

/**
 * Человекочитаемое сообщение из тела ошибки Django/DRF. Поддерживает и общий
 * `{detail}`, и пофайлдовые ошибки сериализатора `{field: ["msg", ...] | "msg"}`
 * (например, при регистрации — правила пароля). Если бэк текста не дал —
 * {@link fallbackErrorMessage} по статусу.
 */
export function extractErrorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.detail === "string") return b.detail;
    const parts: string[] = [];
    for (const v of Object.values(b)) {
      if (typeof v === "string") parts.push(v);
      else if (Array.isArray(v))
        parts.push(...v.filter((x): x is string => typeof x === "string"));
    }
    if (parts.length) return parts.join(" ");
  }
  return fallbackErrorMessage(status);
}

/**
 * Запрос в same-origin BFF. Возвращает разобранный JSON (или undefined для 204).
 * Бросает {@link ApiError} с сообщением из тела Django при не-2xx.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // Content-Type ставим только когда есть тело (GET/DELETE его не несут).
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  if (init?.body != null && !("Content-Type" in headers)) {
    headers["Content-Type"] = "application/json";
  }

  let res: Response;
  try {
    res = await fetch(path, {
      // same-origin (дефолт) — cookie сессии уходят к Next, тот проксирует их в Django.
      credentials: "same-origin",
      ...init,
      headers,
    });
  } catch {
    throw new ApiError("Нет связи с сервером. Проверьте интернет и повторите.", 0);
  }

  if (!res.ok) {
    const body: unknown = await res.json().catch(() => undefined);
    throw new ApiError(extractErrorMessage(body, res.status), res.status, extractErrorCode(body));
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
