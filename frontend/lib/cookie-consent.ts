// Согласие на cookie (DRF-2796).
//
// По умолчанию работают только строго необходимые cookie: сессия (корзина гостя,
// вход), CSRF, признак входа и сама запись выбора. Аналитические (Яндекс.Метрика,
// DRF-2795) включаются только после явного «да». Маркетинговых cookie у сайта нет,
// поэтому и категории такой нет — заводить переключатель «на вырост» значило бы
// спрашивать согласие на то, чего не происходит.
//
// Выбор хранится в cookie, а не в localStorage: это сама по себе строго
// необходимая cookie, её видит сервер (layout решает, показывать ли баннер и
// вставлять ли скрипт уже в серверной разметке — без мигания), и она переживает
// очистку localStorage отдельно от него. Cookie host-only (без Domain): поддоменов
// у сайта нет, dev.proff58.ru редиректит на основной домен.
//
// Версия: при изменении состава категорий или текста согласия CONSENT_VERSION
// поднимается, старая запись считается отсутствующей — баннер показывается снова,
// аналитика выключена до нового ответа. Это правило, а не побочный эффект.

export const CONSENT_COOKIE = "cookie_consent";
export const CONSENT_VERSION = 1;
/** 365 дней: Chrome всё равно режет срок cookie до 400 дней. */
export const CONSENT_MAX_AGE_SECONDS = 365 * 24 * 60 * 60;
/** Событие на window при любой записи/сбросе согласия; detail — Consent | null. */
export const CONSENT_CHANGE_EVENT = "cookie-consent-change";
/** Событие на window: открыть баннер повторно (кнопка «Настройки cookie»). */
export const CONSENT_OPEN_EVENT = "cookie-consent-open";

export type Consent = {
  v: number;
  /** Аналитические cookie (Яндекс.Метрика) разрешены. */
  analytics: boolean;
  /** Момент выбора, мс. */
  ts: number;
};

/** Разбор значения cookie. null — записи нет, она битая или другой версии. */
export function parseConsent(raw: string | null | undefined): Consent | null {
  if (!raw) return null;
  try {
    // Из document.cookie значение приходит закодированным, из cookies() Next — уже
    // раскодированным; для JSON без «%» повторный decode безвреден. Не «чинить».
    const data = JSON.parse(decodeURIComponent(raw)) as Partial<Consent>;
    if (!data || typeof data !== "object") return null;
    if (data.v !== CONSENT_VERSION) return null;
    if (typeof data.analytics !== "boolean") return null;
    return {
      v: CONSENT_VERSION,
      analytics: data.analytics,
      ts: Number(data.ts) || 0,
    };
  } catch {
    return null;
  }
}

export function readRawCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const item = part.trim();
    if (item.startsWith(prefix)) return item.slice(prefix.length);
  }
  return null;
}

/** Текущее согласие посетителя (в браузере). */
export function readConsent(): Consent | null {
  return parseConsent(readRawCookie(CONSENT_COOKIE));
}

function dispatch(consent: Consent | null) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(CONSENT_CHANGE_EVENT, { detail: consent }));
}

/** Записать выбор. Secure — только на https, иначе браузер cookie не примет на локалке. */
export function writeConsent(choice: { analytics: boolean }): Consent {
  const consent: Consent = {
    v: CONSENT_VERSION,
    analytics: choice.analytics,
    ts: Date.now(),
  };
  if (typeof document !== "undefined") {
    const secure =
      typeof location !== "undefined" && location.protocol === "https:" ? "; Secure" : "";
    document.cookie =
      `${CONSENT_COOKIE}=${encodeURIComponent(JSON.stringify(consent))}` +
      `; Max-Age=${CONSENT_MAX_AGE_SECONDS}; Path=/; SameSite=Lax${secure}`;
  }
  dispatch(consent);
  return consent;
}

/** Снять запись (тесты, смена версии). */
export function clearConsent(): void {
  if (typeof document !== "undefined") {
    document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax`;
  }
  dispatch(null);
}

/** Подписка на изменение согласия. Возвращает отписку. */
export function onConsentChange(callback: (consent: Consent | null) => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const handler = (event: Event) => callback((event as CustomEvent<Consent | null>).detail ?? null);
  window.addEventListener(CONSENT_CHANGE_EVENT, handler);
  return () => window.removeEventListener(CONSENT_CHANGE_EVENT, handler);
}

/** Попросить баннер открыться с текущими значениями. */
export function openConsentSettings(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CONSENT_OPEN_EVENT));
}
