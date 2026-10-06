"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { setAnalyticsCounter } from "@/lib/analytics";
import { useConsent, type Consent } from "@/lib/cookie-consent";

// Яндекс.Метрика за согласием (DRF-2795).
//
// Скрипт вставляется только когда посетитель разрешил аналитические cookie; до
// этого ни запросов к mc.yandex.ru, ни cookie `_ym_*` нет. Вебвизор выключен:
// запись сессий — это уже персональные данные. Автохит отключён (defer), просмотры
// отправляем сами: при первом включении и при смене пути. В хит уходит только путь
// без query и без title — в query бывают поисковые запросы, в title страницы заказа
// — имя, а номера заказов и разделы кабинета обобщаются до `*`.
//
// Отзыв согласия: выставляем штатный флаг `disableYaCounter<id>` (если tag.js
// догрузится позже — счётчик не стартует), гасим счётчик, удаляем cookie `_ym_*` и
// ключи `_ym*` в localStorage/sessionStorage (tag.js дублирует там идентификатор и
// восстановил бы cookie из него), и перезагружаем страницу, если скрипт уже был
// вставлен: штатно выгрузить его нельзя. Сама запись выбора к этому моменту уже в
// cookie — её пишет баннер до события.

export const METRIKA_SRC = "https://mc.yandex.ru/metrika/tag.js";
const YM_COOKIES = ["_ym_uid", "_ym_d", "_ym_isad", "_ym_visorc"];

declare global {
  interface Window {
    [key: `disableYaCounter${number}`]: boolean | undefined;
  }
}

/** Путь для хита: без query, идентификаторы заказов и кабинета обобщены. */
export function hitPath(pathname: string): string {
  if (pathname.startsWith("/order/")) return "/order/*";
  if (pathname.startsWith("/account/")) return "/account/*";
  return pathname;
}

function ensureQueue(): NonNullable<Window["ym"]> {
  if (typeof window.ym !== "function") {
    const queued = function (...args: unknown[]) {
      (queued.a = queued.a || []).push(args);
    } as NonNullable<Window["ym"]>;
    queued.l = Date.now();
    window.ym = queued;
  }
  return window.ym;
}

function removeYmCookies() {
  const host = location.hostname;
  const parts = host.split(".");
  // host-only (без Domain) и eTLD+1 с точкой — так tag.js ставит cookie на proff58.ru.
  const domains = [null, parts.length > 2 ? `.${parts.slice(-2).join(".")}` : `.${host}`];
  for (const name of YM_COOKIES) {
    for (const domain of domains) {
      document.cookie = `${name}=; Max-Age=0; Path=/` + (domain ? `; Domain=${domain}` : "");
    }
  }
  for (const storage of [localStorage, sessionStorage]) {
    try {
      const keys: string[] = [];
      for (let i = 0; i < storage.length; i += 1) {
        const key = storage.key(i);
        if (key && key.startsWith("_ym")) keys.push(key);
      }
      keys.forEach((key) => storage.removeItem(key));
    } catch {
      /* хранилище недоступно — удалять нечего */
    }
  }
}

export function YandexMetrika({
  counterId,
  initialConsent,
}: {
  counterId: number;
  initialConsent: Consent | null;
}) {
  const pathname = usePathname() ?? "/";
  const consent = useConsent(initialConsent);
  const enabled = consent?.analytics === true;
  const scriptInserted = useRef(false);
  const wasEnabled = useRef(false);
  const lastHit = useRef<string | null>(null);

  // Включение/отзыв. Включение: очередь ym + init сразу (очередь снимает гонку
  // init/load), скрипт — один раз. Отзыв — только если аналитика была включена.
  useEffect(() => {
    if (enabled) {
      wasEnabled.current = true;
      delete window[`disableYaCounter${counterId}`];
      const ym = ensureQueue();
      if (!scriptInserted.current) {
        ym(counterId, "init", {
          defer: true,
          clickmap: true,
          trackLinks: true,
          accurateTrackBounce: true,
          webvisor: false,
        });
        const script = document.createElement("script");
        script.async = true;
        script.src = METRIKA_SRC;
        document.head.appendChild(script);
        scriptInserted.current = true;
      }
      setAnalyticsCounter(counterId);
      return;
    }

    window[`disableYaCounter${counterId}`] = true;
    setAnalyticsCounter(null);
    // Чистим всегда, а не только при отзыве в этой вкладке: согласие могло истечь,
    // смениться версией или быть отозвано в другой вкладке — старые `_ym_*` не
    // должны жить до года. Удаление идемпотентно и дёшево.
    removeYmCookies();
    if (!wasEnabled.current) return;
    wasEnabled.current = false;
    if (typeof window.ym === "function" && scriptInserted.current) {
      try {
        window.ym(counterId, "destruct");
      } catch {
        /* счётчик уже остановлен */
      }
    }
    if (scriptInserted.current) location.reload();
  }, [enabled, counterId]);

  // Просмотры: первый — при включении, дальше — при смене пути, без дублей.
  useEffect(() => {
    if (!enabled || typeof window.ym !== "function") return;
    const path = hitPath(pathname);
    if (lastHit.current === path) return;
    lastHit.current = path;
    window.ym(counterId, "hit", path);
  }, [enabled, pathname, counterId]);

  return null;
}
