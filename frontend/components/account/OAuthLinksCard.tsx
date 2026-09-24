"use client";

import { useCallback, useEffect, useState } from "react";
import { Check } from "lucide-react";
import { ApiError } from "@/lib/api";
import {
  OAUTH_PROVIDER_LABELS,
  getOAuthAccounts,
  oauthErrorMessage,
  oauthLinkedMessage,
  startOAuthLink,
  unlinkOAuth,
  type OAuthAccount,
  type OAuthProviderId,
} from "@/lib/oauth";
import { VkLogo, YandexLogo } from "./oauth-logos";

// Карточка «Вход через VK ID и Яндекс ID» в ЛК — соседка MaxLinkCard: какие
// провайдеры привязаны, привязать/отвязать. Привязка — POST в BFF за адресом
// провайдера и переход туда; обратно браузер вернётся в профиль с
// ?oauth_linked=<provider> или ?oauth_error=<code>, и это сообщение показываем здесь.

type Flash = { kind: "ok" | "error"; text: string };

// Коды, которыми бэкенд возвращает неудачную привязку в профиль.
const PROFILE_ERROR_CODES = new Set([
  "already_linked",
  "link_expired",
  "failed",
  "unavailable",
  "cancelled",
  "expired",
]);

function Logo({ id }: { id: OAuthProviderId }) {
  return id === "vkid" ? (
    <span className="grid h-7 w-7 place-items-center rounded-md bg-[#0077FF] text-white" aria-hidden>
      <VkLogo className="h-4 w-4" />
    </span>
  ) : (
    <YandexLogo className="h-7 w-7" />
  );
}

/** Сообщение из адреса после возврата от провайдера; null — параметров нет. */
function flashFromUrl(): Flash | null {
  const params = new URLSearchParams(window.location.search);
  const linked = params.get("oauth_linked");
  const error = params.get("oauth_error");
  if (linked !== null) {
    const text = oauthLinkedMessage(linked);
    if (text) return { kind: "ok", text };
  }
  if (error !== null) {
    const code = PROFILE_ERROR_CODES.has(error) ? error : "failed";
    return { kind: "error", text: oauthErrorMessage(code, params.get("provider")) };
  }
  return null;
}

export function OAuthLinksCard() {
  const [accounts, setAccounts] = useState<OAuthAccount[] | null>(null);
  const [busy, setBusy] = useState<OAuthProviderId | null>(null);
  // Сообщение читаем из адреса один раз. Карточка рисуется только в браузере
  // (кабинет показывает её после загрузки профиля), проверка window — страховка.
  const [flash, setFlash] = useState<Flash | null>(() =>
    typeof window === "undefined" ? null : flashFromUrl(),
  );

  useEffect(() => {
    let active = true;
    getOAuthAccounts().then((list) => {
      if (active) setAccounts(list);
    });

    const params = new URLSearchParams(window.location.search);
    if (params.has("oauth_linked") || params.has("oauth_error")) {
      // Убираем параметры из адреса, чтобы обновление страницы не показывало
      // сообщение снова. replaceState, а не router.replace: перерисовывать
      // кабинет ради очистки строки незачем (Next синхронизирует роутер сам).
      for (const key of ["oauth_linked", "oauth_error", "provider"]) params.delete(key);
      const query = params.toString();
      window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
    }
    return () => {
      active = false;
    };
  }, []);

  const link = useCallback(async (id: OAuthProviderId) => {
    setBusy(id);
    setFlash(null);
    try {
      const url = await startOAuthLink(id);
      window.location.assign(url);
      // busy не снимаем: страница уходит к провайдеру.
    } catch (e) {
      setFlash({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Не удалось начать привязку. Попробуйте ещё раз.",
      });
      setBusy(null);
    }
  }, []);

  const unlink = useCallback(async (id: OAuthProviderId) => {
    if (!window.confirm(`Отвязать ${OAUTH_PROVIDER_LABELS[id]}?`)) return;
    setBusy(id);
    setFlash(null);
    try {
      await unlinkOAuth(id);
      setAccounts(await getOAuthAccounts());
    } catch (e) {
      setFlash({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Не удалось отвязать. Попробуйте ещё раз.",
      });
    } finally {
      setBusy(null);
    }
  }, []);

  const hasAccounts = accounts !== null && accounts.length > 0;
  // Нет включённых провайдеров — карточки нет; сообщение о возврате от
  // провайдера всё равно показываем (например, «способ недоступен»).
  if (!hasAccounts && !flash) return null;

  return (
    <div className="mt-6 border-t border-line pt-4">
      <h2 className="mb-2 font-semibold text-ink">Вход через VK ID и Яндекс ID</h2>

      {flash && (
        <p
          role={flash.kind === "error" ? "alert" : "status"}
          className={
            flash.kind === "error"
              ? "mb-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
              : "mb-3 flex items-center gap-2 rounded-md border border-accent/30 bg-accent/10 px-3 py-2 text-sm text-ink"
          }
        >
          {flash.kind === "ok" && <Check className="h-4 w-4 shrink-0 text-accent" aria-hidden />}
          {flash.text}
        </p>
      )}

      {hasAccounts && (
        <ul className="space-y-3">
          {accounts.map((acc) => {
            const label = OAUTH_PROVIDER_LABELS[acc.id];
            const hintId = `oauth-${acc.id}-hint`;
            return (
              <li key={acc.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
                <span className="flex min-w-0 items-center gap-2">
                  <Logo id={acc.id} />
                  <span className="font-medium text-ink">{label}</span>
                </span>
                {acc.linked ? (
                  <>
                    <span className="min-w-0 break-all text-ink-2">
                      Привязан{acc.email ? ` · ${acc.email}` : ""}
                    </span>
                    <button
                      type="button"
                      onClick={() => unlink(acc.id)}
                      disabled={busy !== null || !acc.can_unlink}
                      aria-label={`Отвязать ${label}`}
                      aria-describedby={acc.can_unlink ? undefined : hintId}
                      title={acc.can_unlink ? undefined : "Единственный способ входа"}
                      className="text-danger underline disabled:cursor-not-allowed disabled:opacity-50 disabled:no-underline"
                    >
                      Отвязать
                    </button>
                    {!acc.can_unlink && (
                      <span id={hintId} className="text-xs text-ink-3">
                        Единственный способ входа
                      </span>
                    )}
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => link(acc.id)}
                    disabled={busy !== null}
                    aria-label={`Привязать ${label}`}
                    className="inline-flex min-h-9 items-center rounded-md border border-line px-3 font-semibold text-ink transition hover:bg-raised disabled:opacity-50"
                  >
                    {busy === acc.id ? "Переходим…" : "Привязать"}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {hasAccounts && accounts.some((a) => a.id === "vkid") && (
        <p className="mt-2 text-xs text-ink-3">Вход через Mail — это тоже VK ID.</p>
      )}
    </div>
  );
}
