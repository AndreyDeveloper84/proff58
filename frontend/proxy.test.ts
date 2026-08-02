import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { config, proxy } from "./proxy";

// Кабинет — клиентский и предрендеренный, поэтому без серверной отсечки гость
// успевал увидеть чужой «Личный кабинет» на 1,5–7 секунд, прежде чем браузер
// уводил его на вход. Здесь проверяем саму отсечку.

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

  it("с cookie сессии пропускает дальше", () => {
    const res = proxy(request("/account/profile", "sessionid=abc123"));

    expect(res.headers.get("location")).toBeNull();
    expect(res.status).toBe(200);
  });

  it("сама форма входа исключена из matcher", () => {
    // Иначе редирект зациклится: /account/login → /account/login → …
    // Роутинг здесь не воспроизводим — проверяем ровно то, что отдаём Next.
    expect(config.matcher).toEqual(["/account", "/account/((?!login).*)"]);
  });
});
