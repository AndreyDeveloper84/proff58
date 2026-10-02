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
  // Весь кабинет, кроме страниц, которые открывают без входа:
  // - login — форма входа (иначе редирект зациклится);
  // - wishlist — старый адрес избранного: оно переехало на витрину и входа не
  //   требует, страница по прежнему адресу просто уводит на /wishlist;
  // - forgot-password и reset-password — восстановление пароля. Сюда приходят
  //   как раз те, кто войти не может, часто по ссылке из письма в другом
  //   браузере, где нет ни одной cookie (DRF-2732: guard уводил их на вход).
  matcher: ["/account", "/account/((?!login|wishlist|forgot-password|reset-password).*)"],
};
