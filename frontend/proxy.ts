import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Серверная защита личного кабинета (Next 16: бывший middleware называется proxy).
//
// Зачем: страницы кабинета — клиентские и предрендеренные, поэтому анонимному
// посетителю сервер отдавал полностью готовую страницу «Личный кабинет», и лишь
// через 1,5–7 с браузер узнавал, что пользователя нет, и уводил на форму входа.
// Человек успевал прочитать чужой интерфейс и решить, что его «разлогинило».
//
// Проверка здесь намеренно оптимистичная — только наличие cookie сессии, без
// обращения к Django: proxy стоит на пути каждого запроса, и поход в бэкенд
// добавил бы задержку всему кабинету (об этом же предупреждает документация
// Next: proxy — не место для полноценной авторизации). Настоящую проверку и
// дальше делает страница через /api/account/me/; здесь мы лишь отсекаем
// заведомых гостей — то есть подавляющее большинство случаев.
//
// Куда человек шёл, сохраняем в ?next= — форма входа умеет туда вернуть.

/** Cookie сессии Django (SESSION_COOKIE_NAME по умолчанию). */
const SESSION_COOKIE = "sessionid";

const LOGIN_PATH = "/account/login";

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();

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
