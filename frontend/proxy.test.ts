import { readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { config, proxy } from "./proxy";

// Кабинет — клиентский и предрендеренный, поэтому без серверной отсечки гость
// успевал увидеть чужой «Личный кабинет» на 1,5–7 секунд, прежде чем браузер
// уводил его на вход. Здесь проверяем быстрый отсев; настоящую проверку делает
// layout кабинета (lib/server-auth.ts).

function request(path: string, cookie?: string) {
  return new NextRequest(new URL(`https://proff58.ru${path}`), {
    headers: cookie ? { cookie } : undefined,
  });
}

describe("proxy: доступ в личный кабинет", () => {
  it("гостя уводит на вход и запоминает, куда он шёл", () => {
    const res = proxy(request("/account/orders"));
    const location = new URL(res.headers.get("location") ?? "");

    expect(res.status).toBe(307);
    expect(location.pathname).toBe("/account/login");
    expect(location.searchParams.get("next")).toBe("/account/orders");
  });

  it("сохраняет параметры адреса в next", () => {
    const res = proxy(request("/account/orders?tab=delivered"));
    const location = new URL(res.headers.get("location") ?? "");

    expect(location.searchParams.get("next")).toBe("/account/orders?tab=delivered");
  });

  it("с маркером входа пропускает дальше", () => {
    const res = proxy(request("/account/profile", "auth=1"));

    expect(res.headers.get("location")).toBeNull();
    expect(res.status).toBe(200);
  });

  it("гостевую сессию корзины пропускает — но решать будет layout", () => {
    // Сама по себе `sessionid` входом не является: Django выдаёт её и анониму.
    // Раньше по ней proxy пускал внутрь, и гость видел разметку кабинета.
    // Пропуск здесь оставлен ради тех, кто вошёл до появления маркера.
    const res = proxy(request("/account/profile", "sessionid=abc123"));

    expect(res.headers.get("location")).toBeNull();
    expect(res.status).toBe(200);
  });

  it("передаёт адрес в x-pathname — layout вернёт человека туда после входа", () => {
    const res = proxy(request("/account/invoices?page=2", "auth=1"));

    expect(res.headers.get("x-middleware-request-x-pathname")).toBe("/account/invoices");
  });

  it("страницы без входа исключены из matcher", () => {
    // login — иначе редирект зациклится: /account/login → /account/login → …
    // wishlist — избранное переехало на витрину и входа не требует; страница по
    // прежнему адресу уводит на /wishlist, и разворачивать гостя раньше неё нельзя.
    // forgot-password, reset-password — восстановление пароля (DRF-2732).
    // Роутинг здесь не воспроизводим — проверяем ровно то, что отдаём Next.
    expect(config.matcher).toEqual([
      "/account",
      "/account/((?!login|wishlist|forgot-password|reset-password).*)",
    ]);
  });

  // Регулярка matcher'а — то место, где легко ошибиться скобкой, поэтому
  // проверяем её на самих адресах.
  it("регулярка matcher пропускает вход и избранное, но ловит остальной кабинет", () => {
    const rule = new RegExp(`^${config.matcher[1]}$`);

    expect(rule.test("/account/login")).toBe(false);
    expect(rule.test("/account/wishlist")).toBe(false);
    expect(rule.test("/account/profile")).toBe(true);
    expect(rule.test("/account/orders/PROF-12")).toBe(true);
  });

  // DRF-2732: guard уводил на вход того, кто пароль забыл. Ссылку из письма
  // открывают в браузере без единой cookie — раньше это маскировала сессия
  // гостевой корзины, которую Django выдавал каждому.
  it("восстановление пароля открыто без входа", () => {
    const rule = new RegExp(`^${config.matcher[1]}$`);

    expect(rule.test("/account/forgot-password")).toBe(false);
    expect(rule.test("/account/reset-password")).toBe(false);
  });

  it("каждая страница кабинета вне группы (guarded) исключена из matcher", () => {
    // Страница под app/account/, которой нет в (guarded), открыта без входа по
    // замыслу. Забыть её в matcher — значит молча закрыть: так и случилось с
    // восстановлением пароля. Список сверяем с файловой системой.
    const rule = new RegExp(`^${config.matcher[1]}$`);
    const open = readdirSync(join(process.cwd(), "app", "account"), { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && !entry.name.startsWith("("))
      .map((entry) => entry.name);

    expect(open.length).toBeGreaterThan(0);
    for (const name of open) expect(rule.test(`/account/${name}`), name).toBe(false);
  });
});
