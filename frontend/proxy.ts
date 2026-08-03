import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { authStateFromCookies, loginHref } from "@/lib/auth-state";

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
// кабинет. Теперь состояние считается по обеим cookie (lib/auth-state) — тем же
// правилом, что и ссылки в шапке, чтобы они не расходились.
//
// Куда человек шёл, кладём в ?next= (для редиректа) и в x-pathname — серверному
// layout адрес запроса иначе недоступен.

export function proxy(request: NextRequest) {
  // "unknown" (сессия есть, маркера нет) пропускаем: у тех, кто вошёл до
  // появления маркера, его ещё нет, и выбрасывать их на форму входа нельзя.
  const state = authStateFromCookies((name) => request.cookies.has(name));

  if (state !== "anonymous") {
    const headers = new Headers(request.headers);
    headers.set("x-pathname", request.nextUrl.pathname);
    return NextResponse.next({ request: { headers } });
  }

  const next = request.nextUrl.pathname + request.nextUrl.search;
  return NextResponse.redirect(new URL(loginHref(next), request.nextUrl));
}

export const config = {
  // Весь кабинет, кроме самой формы входа (иначе редирект зациклится).
  matcher: ["/account", "/account/((?!login).*)"],
};
