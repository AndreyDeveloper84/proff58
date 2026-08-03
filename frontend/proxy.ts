import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Быстрый отсев гостей на подступах к кабинету (Next 16: бывший middleware).
//
// Настоящую проверку делает серверный layout кабинета (lib/server-auth.ts) — он
// спрашивает у Django, кто это. Здесь мы лишь экономим тот запрос тем, у кого
// входа заведомо нет: proxy стоит на пути каждого обращения к кабинету, и поход
// в бэкенд отсюда стоил бы дороже.
//
// Почему не `sessionid`. Раньше признаком входа считалась именно она — и это
// было ошибкой: Django заводит сессию и анонимному посетителю (гостевая
// корзина), поэтому cookie появлялась почти у всех, а proxy пропускал их в
// кабинет. Теперь смотрим на маркер, который Django ставит по факту входа
// (apps/accounts/middleware.py).
//
// Куда человек шёл, кладём в ?next= (для редиректа) и в x-pathname — серверному
// layout адрес запроса иначе недоступен.

/** Маркер входа: Django ставит его при входе и снимает при выходе. */
const AUTH_MARKER_COOKIE = "auth";

/**
 * Сессия Django. Не признак входа, но признак «возможно, вошёл»: у тех, кто был
 * залогинен до появления маркера, его ещё нет. Таких пропускаем к настоящей
 * проверке, а не выбрасываем на форму входа. Условие можно снять, когда истекут
 * сессии той поры (SESSION_COOKIE_AGE — две недели).
 */
const SESSION_COOKIE = "sessionid";

const LOGIN_PATH = "/account/login";

export function proxy(request: NextRequest) {
  const mayBeAuthenticated =
    request.cookies.has(AUTH_MARKER_COOKIE) || request.cookies.has(SESSION_COOKIE);

  if (mayBeAuthenticated) {
    const headers = new Headers(request.headers);
    headers.set("x-pathname", request.nextUrl.pathname);
    return NextResponse.next({ request: { headers } });
  }

  const url = request.nextUrl.clone();
  const next = request.nextUrl.pathname + request.nextUrl.search;
  url.pathname = LOGIN_PATH;
  url.search = "";
  url.searchParams.set("next", next);
  return NextResponse.redirect(url);
}

export const config = {
  // Весь кабинет, кроме самой формы входа (иначе редирект зациклится).
  matcher: ["/account", "/account/((?!login).*)"],
};
