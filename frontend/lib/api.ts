// Клиентский fetch-хелпер для обращений браузера в same-origin BFF (/api/**, #246).
// Только клиентская сторона: cookie сессии отправляются автоматически (same-origin).
// Серверные обращения к Django живут отдельно (lib/adapters.ts, lib/bff.ts) — не дублируем.

// Ошибка обращения к BFF: несёт HTTP-статус и человекочитаемый detail из ответа Django.
export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Запрос в same-origin BFF. Возвращает разобранный JSON (или undefined для 204).
 * Бросает {@link ApiError} с detail из тела Django при не-2xx.
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
    throw new ApiError("Нет связи с сервером.", 0);
  }

  if (!res.ok) {
    const detail = await res
      .json()
      .then((b: { detail?: string }) => b?.detail)
      .catch(() => undefined);
    throw new ApiError(detail ?? `Ошибка ${res.status}.`, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
