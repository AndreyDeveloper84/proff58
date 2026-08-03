// Куда вести ссылки кабинета: вошёл ли посетитель — насколько это видно по cookie.
//
// Три состояния, а не два. Раньше здесь был один признак «есть маркер входа», и
// его отсутствие считалось «это гость». Но маркер (cookie `auth`, ставит
// apps/accounts/middleware.py) появляется только после ответа Django, а сессия
// живёт своей жизнью и может быть старше маркера — например, человек вошёл до
// того, как маркер вообще появился на сервере. Такой посетитель залогинен, но
// маркера у него нет, и шапка честно вела его на форму входа: «показало экран
// входа, хотя я был залогинен, а после перезагрузки всё нормально».
//
//   authenticated — маркер есть, точно вошёл;
//   unknown       — маркера нет, но есть сессионная cookie: может быть и вошёл.
//                   Ведём как обычно, настоящую проверку делает гвард кабинета;
//   anonymous     — cookie нет вовсе. Только здесь ссылка идёт сразу на вход.
//
// Считается на сервере (app/layout.tsx читает cookies()), потому что сессионная
// cookie — HttpOnly, из браузера её не видно. Заодно ссылки правильны уже в
// серверной разметке: раньше они «доводились» после гидратации и до неё вели не
// туда.

export type AuthState = "authenticated" | "unknown" | "anonymous";

/** Маркер входа. Не HttpOnly — его читает интерфейс (см. accounts/middleware.py). */
export const AUTH_MARKER_COOKIE = "auth";

/** Сессия Django. HttpOnly: доступна только серверу — отсюда и серверный расчёт. */
export const SESSION_COOKIE = "sessionid";

/**
 * Состояние входа по наличию cookie.
 *
 * @param has предикат «есть такая cookie» (cookies() на сервере, request.cookies в proxy).
 */
export function authStateFromCookies(has: (name: string) => boolean): AuthState {
  if (has(AUTH_MARKER_COOKIE)) return "authenticated";
  if (has(SESSION_COOKIE)) return "unknown";
  return "anonymous";
}

/**
 * Адрес формы входа с запоминанием, куда человек шёл (форма вернёт его туда).
 *
 * Живёт здесь, а не в lib/auth: этот модуль ни от чего не зависит, поэтому его
 * может импортировать и proxy.ts, которому API-клиент в бандле не нужен.
 */
export function loginHref(next?: string): string {
  return next && next.startsWith("/")
    ? `/account/login?next=${encodeURIComponent(next)}`
    : "/account/login";
}

/**
 * Адрес ссылки в кабинет: гостя ведём сразу на форму входа с возвратом.
 *
 * Гостя — значит именно гостя (`anonymous`). При `unknown` ссылка ведёт по
 * назначению: ошибиться в сторону «пустить и проверить» безопасно (гварда никто
 * не отменял), а ошибиться в сторону «на вход» — значит отправить туда вошедшего.
 */
export function accountLinkHref(path: string, state: AuthState): string {
  return state === "anonymous" ? loginHref(path) : path;
}
