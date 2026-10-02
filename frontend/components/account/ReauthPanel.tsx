"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { LoaderCircle, ShieldCheck } from "lucide-react";
import { MaxAuthFlow } from "@/components/account/MaxAuthFlow";
import { MAX_REAUTH_FAILURES } from "@/lib/max-auth-messages";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { maxAccountStatus, maxReauthStart, reauthPassword } from "@/lib/auth";
import {
  OAUTH_PROVIDER_LABELS,
  getOAuthAccounts,
  startOAuthReauth,
  type OAuthProviderId,
} from "@/lib/oauth";

// «Подтвердите, что это вы» (DRF-2497). Сервер ответил reauth_required на опасное
// действие — удаление аккаунта, смену e-mail, привязку способа входа. Показываем
// только те способы, которые у человека есть: у кого пароль — пароль (вход через
// провайдера для них не в счёт); у кого нет — привязанный MAX, VK ID, Яндекс ID.
// Если подтвердить нечем — не тупик, а контакты магазина.

type Methods = { max: boolean; oauth: OAuthProviderId[] };

export function ReauthPanel({
  hasPassword,
  next,
  onVerified,
}: {
  hasPassword: boolean;
  /** Куда вернуть после подтверждения через VK ID / Яндекс ID (путь кабинета). */
  next: string;
  /** Подтверждено паролем или через MAX — можно повторить действие. */
  onVerified: () => void;
}) {
  const [methods, setMethods] = useState<Methods | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (hasPassword) return;
    let active = true;
    Promise.all([maxAccountStatus(), getOAuthAccounts()])
      .then(([max, accounts]) => {
        if (!active) return;
        setMethods({ max: max.linked, oauth: accounts.filter((a) => a.linked).map((a) => a.id) });
      })
      .catch(() => {
        if (active) setMethods({ max: false, oauth: [] });
      });
    return () => {
      active = false;
    };
  }, [hasPassword]);

  const submitPassword = async (event: FormEvent) => {
    event.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError("");
    try {
      await reauthPassword(password);
      onVerified();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Не удалось подтвердить.");
      setBusy(false);
    }
  };

  const viaProvider = async (provider: OAuthProviderId) => {
    setBusy(true);
    setError("");
    try {
      window.location.assign(await startOAuthReauth(provider, next));
      // busy не снимаем: страница уходит к провайдеру.
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Не удалось начать подтверждение.");
      setBusy(false);
    }
  };

  const loading = !hasPassword && methods === null;
  const nothing = !hasPassword && methods !== null && !methods.max && methods.oauth.length === 0;

  return (
    <section
      aria-labelledby="reauth-title"
      className="space-y-3 rounded-md border border-accent/30 bg-accent/5 p-4"
    >
      <div className="flex items-start gap-2">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
        <div>
          <h3 id="reauth-title" className="text-sm font-semibold text-ink">
            Подтвердите, что это вы
          </h3>
          <p className="mt-0.5 text-xs leading-5 text-ink-3">
            {hasPassword
              ? "Введите пароль от аккаунта."
              : "Войдите ещё раз тем способом, которым входите обычно. Подтверждение действует 10 минут."}
          </p>
        </div>
      </div>

      {hasPassword && (
        <form onSubmit={submitPassword} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Field label="Пароль" required>
              {(control) => (
                <Input
                  {...control}
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                />
              )}
            </Field>
          </div>
          <button
            type="submit"
            disabled={!password || busy}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
          >
            {busy && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
            Подтвердить
          </button>
        </form>
      )}

      {loading && <p className="text-sm text-ink-3">Проверяем способы входа…</p>}

      {methods?.max && (
        <MaxAuthFlow
          start={maxReauthStart}
          ctaLabel="Подтвердить через MAX"
          failureMessages={MAX_REAUTH_FAILURES}
          onCompleted={onVerified}
        />
      )}

      {methods && methods.oauth.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {methods.oauth.map((provider) => (
            <button
              key={provider}
              type="button"
              onClick={() => void viaProvider(provider)}
              disabled={busy}
              className="inline-flex min-h-10 items-center rounded-md border border-line bg-surface px-4 text-sm font-semibold text-ink transition hover:bg-raised disabled:opacity-50"
            >
              Подтвердить через {OAUTH_PROVIDER_LABELS[provider]}
            </button>
          ))}
        </div>
      )}

      {nothing && (
        <p className="text-sm leading-6 text-ink-2">
          Подтвердить вход сейчас нечем. Свяжитесь с магазином — поможем:{" "}
          <Link href="/info/about" className="font-semibold text-accent hover:underline">
            контакты
          </Link>
          .
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {error}
        </p>
      )}
    </section>
  );
}
