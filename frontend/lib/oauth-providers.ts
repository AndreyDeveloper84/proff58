// Какие провайдеры входа включены — для серверной отрисовки страницы входа.
//
// Только server-side: ходит в Django напрямую по INTERNAL_API_BASE_URL, как
// lib/info-pages.ts. Любая беда (нет адреса, таймаут, 5xx, мусор в ответе) —
// пустой список: страница рисуется без соцкнопок, а не падает, и кнопки
// «в никуда» не появляются.
import { pickProviders, type OAuthProviderId } from "./oauth";
import { ssrHeaders } from "./ssr";

// Зависший апстрим не должен вешать форму входа.
const SSR_TIMEOUT_MS = 4000;

export async function getLoginOAuthProviders(): Promise<OAuthProviderId[]> {
  // Читаем при вызове: адрес приходит в рантайме контейнера, а не на сборке.
  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base) return [];
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}/api/oauth/providers/`, {
      cache: "no-store",
      headers: ssrHeaders(),
      signal: AbortSignal.timeout(SSR_TIMEOUT_MS),
    });
    if (!res.ok) return [];
    const json = (await res.json()) as { providers?: unknown } | null;
    return pickProviders(json?.providers);
  } catch {
    return [];
  }
}
