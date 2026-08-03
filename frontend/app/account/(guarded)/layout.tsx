import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { loginHref } from "@/lib/auth";
import { checkServerAuth } from "@/lib/server-auth";

// Гвард личного кабинета: решение принимается на сервере, до отдачи HTML.
//
// Группа (guarded) существует ради того, чтобы этот layout НЕ накрыл
// /account/login — иначе форма входа гоняла бы гостя редиректом по кругу.
// Адреса от группы не меняются: /account/(guarded)/orders → /account/orders.
//
// Страницы кабинета остаются клиентскими и по-прежнему сами зовут checkAuth():
// им нужен профиль, а не только факт входа. Здесь мы отвечаем на другой вопрос —
// показывать ли этому посетителю разметку кабинета вообще.

export default async function GuardedAccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const requestHeaders = await headers();
  const state = await checkServerAuth(requestHeaders.get("cookie") ?? "");

  if (state === "anonymous") {
    // Куда человек шёл — proxy кладёт в x-pathname (в layout адрес недоступен).
    redirect(loginHref(requestHeaders.get("x-pathname") ?? undefined));
  }

  // state === "unavailable" — пускаем внутрь: сбой связи не повод выкидывать
  // человека с живой сессией, страница сама скажет, что сервис недоступен.
  return <>{children}</>;
}
