"use client";

// Маркер входа для интерфейса: по нему ссылки в шапке ведут гостя сразу на форму
// входа, а не в кабинет.
//
// Зачем. Раньше «Кабинет» и «Избранное» вели в кабинет всем подряд. Гвард
// разворачивал гостя уже на сервере — но при клиентской навигации Next успевал
// сменить адрес на /account/profile, а редирект приезжал следом внутри
// RSC-ответа. Человек видел скачок в адресной строке и пустую страницу на месте
// сайта. Правильная ссылка снимает это: гостю — один переход сразу на вход.
//
// Маркер ставит Django по факту входа (apps/accounts/middleware.py) и снимает на
// выходе. Доступа он не даёт: кабинет защищён сессией и серверной проверкой, а
// здесь решается только то, куда вести по ссылке.

import { useCallback, useSyncExternalStore } from "react";

import { loginHref } from "@/lib/auth";

const AUTH_MARKER_COOKIE = "auth";

function readMarker(): boolean {
  return document.cookie.split("; ").some((pair) => pair.startsWith(`${AUTH_MARKER_COOKIE}=`));
}

/**
 * Есть ли маркер входа.
 *
 * `null` — «ещё не знаем»: на сервере cookie браузера не читаются, а первый
 * рендер клиента обязан совпасть с серверной разметкой. Поэтому неизвестность
 * трактуется как «веди как раньше», а поправка приходит сразу после гидратации.
 *
 * Чтение — через useSyncExternalStore (тот же приём, что для снимка заказа на
 * странице благодарности): это и есть внешний источник, и он даёт корректный
 * серверный снимок без рассинхрона гидратации. Подписки нет — cookie об
 * изменениях не уведомляет, а вход и выход и без того перезагружают маршрут.
 */
export function useHasAuthMarker(): boolean | null {
  const subscribe = useCallback(() => () => {}, []);
  return useSyncExternalStore(subscribe, readMarker, () => null);
}

/**
 * Куда вести по ссылке в кабинет: гостя — на форму входа с возвратом.
 *
 * @param path   адрес внутри кабинета (куда человек на самом деле шёл)
 * @param marker результат {@link useHasAuthMarker}
 */
export function accountLinkHref(path: string, marker: boolean | null): string {
  return marker === false ? loginHref(path) : path;
}
