// Согласие на cookie как внешнее хранилище для React (DRF-2796).
//
// Отдельный модуль, а не часть lib/cookie-consent.ts: тот импортирует серверный
// app/layout.tsx (читает cookie на сервере), а useSyncExternalStore доступен только в
// клиентских модулях — Turbopack падает на сборке, если хук лежит рядом.
//
// useSyncExternalStore вместо «useState + useEffect(setState)»: источник правды —
// cookie, события о её смене уже есть, а серверный снимок (initialConsent из layout)
// совпадает с клиентским у согласившегося, поэтому гидрация без мигания и без
// setState внутри эффекта (react-hooks/set-state-in-effect).

import { useMemo, useSyncExternalStore } from "react";

import {
  CONSENT_CHANGE_EVENT,
  CONSENT_COOKIE,
  parseConsent,
  readRawCookie,
  type Consent,
} from "./cookie-consent";

function subscribe(callback: () => void): () => void {
  window.addEventListener(CONSENT_CHANGE_EVENT, callback);
  return () => window.removeEventListener(CONSENT_CHANGE_EVENT, callback);
}

function rawSnapshot(): string {
  return readRawCookie(CONSENT_COOKIE) ?? "";
}

/** Текущее согласие в компоненте; `initial` — то, что прочитал сервер из cookie. */
export function useConsent(initial: Consent | null): Consent | null {
  const raw = useSyncExternalStore(subscribe, rawSnapshot, () =>
    initial ? encodeURIComponent(JSON.stringify(initial)) : "",
  );
  return useMemo(() => parseConsent(raw), [raw]);
}
