// Вход и привязка через VK ID (+ Mail) и Яндекс ID.
//
// Общая часть для страницы входа (серверная и клиентская половины) и кабинета:
// белый список провайдеров, подписи, тексты ошибок `?oauth_error=` и адреса
// старта. Контракт с бэкендом — scratchpad/OAUTH-CONTRACT.md (apps/integration_oauth).
//
// Вход идёт ОБЫЧНОЙ навигацией браузера на `/api/oauth/<provider>/start/`:
// nginx отдаёт этот путь Django напрямую, тот ставит state в сессию и уводит
// 302 на провайдера. fetch здесь не годится — нужен переход верхнего уровня.
// Кабинетные вызовы (список привязок, привязать, отвязать) — через BFF
// `/api/account/oauth/**`, как и остальной кабинет (CSRF добавляет lib/bff.ts).
import { ApiError, apiFetch } from "@/lib/api";

/** Провайдеры, которые фронт умеет показывать. Всё остальное из URL/API — игнор. */
export const OAUTH_PROVIDERS = ["vkid", "yandex"] as const;
export type OAuthProviderId = (typeof OAUTH_PROVIDERS)[number];

export const OAUTH_PROVIDER_LABELS: Record<OAuthProviderId, string> = {
  vkid: "VK ID",
  yandex: "Яндекс ID",
};

export function isOAuthProvider(value: unknown): value is OAuthProviderId {
  return typeof value === "string" && (OAUTH_PROVIDERS as readonly string[]).includes(value);
}

/**
 * Адрес старта входа через провайдера.
 *
 * `via=mail_ru` — вход через Mail: это тот же VK ID (одна учётка, один
 * `user_id`), провайдер лишь открывает свою форму на вкладке Mail.
 * `next` — уже проверенный путь сайта (см. safeNextPath); нет — параметр не пишем,
 * бэкенд тогда вернёт в профиль.
 */
export function oauthStartHref(
  provider: OAuthProviderId,
  opts: { via?: "mail_ru"; next?: string | null } = {},
): string {
  const params: string[] = [];
  if (opts.via) params.push(`via=${opts.via}`);
  if (opts.next) params.push(`next=${encodeURIComponent(opts.next)}`);
  return `/api/oauth/${provider}/start/${params.length ? `?${params.join("&")}` : ""}`;
}

// Тексты по кодам из контракта. {p} — подпись провайдера из белого списка.
const ERROR_TEXTS: Record<string, (p: string | null) => string> = {
  cancelled: () => "Вход отменён.",
  failed: () => "Не удалось войти. Попробуйте ещё раз или выберите другой способ.",
  unavailable: () => "Этот способ входа сейчас недоступен.",
  rate_limited: () => "Слишком много попыток. Подождите минуту и попробуйте снова.",
  expired: () => "Время на вход истекло. Попробуйте ещё раз.",
  email_exists: (p) =>
    `Аккаунт с этой почтой уже есть. Войдите паролем или через MAX, затем привяжите ${
      p ?? "этот способ входа"
    } в личном кабинете.`,
  no_email: (p) =>
    `${p ?? "Сервис входа"} не передал адрес почты. Разрешите доступ к почте или войдите другим способом.`,
  inactive: () => "Аккаунт удалён или заблокирован.",
  already_linked: (p) =>
    p
      ? `Этот ${p} уже привязан к другому аккаунту.`
      : "Этот способ входа уже привязан к другому аккаунту.",
  link_expired: () => "Привязка не завершена: войдите в аккаунт и попробуйте снова.",
};

/**
 * Текст для `?oauth_error=<code>&provider=<id>`.
 *
 * Код и провайдер приходят из адресной строки, то есть их может подставить кто
 * угодно: в текст попадают только наши заготовки, неизвестный код — общий
 * `failed`, чужой провайдер — нейтральная формулировка без него.
 */
export function oauthErrorMessage(code: string | null | undefined, provider?: string | null) {
  const label = isOAuthProvider(provider) ? OAUTH_PROVIDER_LABELS[provider] : null;
  const text =
    code && Object.prototype.hasOwnProperty.call(ERROR_TEXTS, code)
      ? ERROR_TEXTS[code]
      : ERROR_TEXTS.failed;
  return text(label);
}

/** Сообщение после успешной привязки (`?oauth_linked=<provider>`); чужой провайдер — null. */
export function oauthLinkedMessage(provider: string | null | undefined): string | null {
  return isOAuthProvider(provider)
    ? `${OAUTH_PROVIDER_LABELS[provider]} привязан — теперь можно входить через него.`
    : null;
}

/** Список провайдеров, пришедший от сервера, → только известные, без дублей, в нашем порядке. */
export function pickProviders(raw: unknown): OAuthProviderId[] {
  const list = Array.isArray(raw) ? raw : [];
  const ids = new Set(
    list.map((item) => (item && typeof item === "object" ? (item as { id?: unknown }).id : null)),
  );
  return OAUTH_PROVIDERS.filter((p) => ids.has(p));
}

// --- Кабинет: привязки ---

export type OAuthAccount = {
  id: OAuthProviderId;
  linked: boolean;
  email: string;
  linked_at: string | null;
  /** false — это единственный способ входа, отвязывать нельзя. */
  can_unlink: boolean;
};

/**
 * Привязки текущего пользователя по включённым провайдерам.
 *
 * Сбой — пустой список: карточка тогда просто не рисуется, как и при
 * выключенном входе через провайдеров (так же ведёт себя статус MAX).
 */
export async function getOAuthAccounts(): Promise<OAuthAccount[]> {
  try {
    const data = await apiFetch<{ providers?: unknown }>("/api/account/oauth", { method: "GET" });
    const list = Array.isArray(data?.providers) ? (data.providers as OAuthAccount[]) : [];
    return OAUTH_PROVIDERS.flatMap((p) => {
      const row = list.find((item) => item && item.id === p);
      return row ? [row] : [];
    });
  } catch (e) {
    if (e instanceof ApiError) return [];
    throw e;
  }
}

/**
 * Начать привязку: сервер кладёт state в сессию и отдаёт адрес провайдера.
 * Переходить по нему — `window.location.assign`, вернётся браузер в профиль.
 */
export async function startOAuthLink(provider: OAuthProviderId): Promise<string> {
  const data = await apiFetch<{ url?: unknown }>(`/api/account/oauth/${provider}/link`, {
    method: "POST",
  });
  const url = typeof data?.url === "string" ? data.url : "";
  // Уводим только на https: адрес приходит от нашего сервера, но переход на
  // javascript:/data: из-за чужой ошибки обошёлся бы слишком дорого.
  if (!/^https:\/\//i.test(url)) {
    throw new ApiError("Не удалось начать привязку. Попробуйте ещё раз.", 0);
  }
  return url;
}

export async function unlinkOAuth(provider: OAuthProviderId): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/account/oauth/${provider}/unlink`, { method: "POST" });
}
