"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import { confirmPasswordReset } from "@/lib/auth";
import { ErrorState, SuccessState } from "@/components/ui/states";

const INPUT =
  "mt-1 h-11 w-full rounded-md border border-line bg-surface px-3 text-ink outline-none focus:border-accent";

function RequestAgain() {
  return (
    <Link href="/account/forgot-password" className="font-medium text-accent hover:underline">
      Запросить письмо заново
    </Link>
  );
}

export function ResetPasswordForm({ uid, token }: { uid: string; token: string }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");
  const [invalid, setInvalid] = useState(!uid || !token);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  if (invalid) {
    return (
      <ErrorState
        title="Ссылка недействительна или устарела"
        description="Ссылка из письма действует один час и подходит только один раз."
        action={<RequestAgain />}
      />
    );
  }

  if (done) {
    return (
      <SuccessState
        title="Пароль изменён"
        description="Войдите с новым паролем. На других устройствах потребуется войти заново."
        action={
          <Link href="/account/login" className="font-medium text-accent hover:underline">
            Войти
          </Link>
        }
      />
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== repeat) return setError("Пароли не совпадают.");
    setLoading(true);
    try {
      await confirmPasswordReset(uid, token, password);
      setDone(true);
      // Токен одноразовый, но в адресной строке и истории ему делать нечего.
      router.replace("/account/reset-password?done=1");
    } catch (err: unknown) {
      if (err instanceof ApiError && err.code === "invalid_token") {
        setInvalid(true);
      } else {
        setError(err instanceof Error ? err.message : "Ошибка");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h1 className="text-2xl font-semibold text-ink">Новый пароль</h1>
      <p className="mt-1 text-sm text-ink-3">Минимум 8 символов, не только цифры.</p>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <label className="block text-sm text-ink-2">
          Новый пароль
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={INPUT}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </label>
        <label className="block text-sm text-ink-2">
          Повторите пароль
          <input
            type="password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            className={INPUT}
            required
            autoComplete="new-password"
          />
        </label>
        {error && (
          <p role="alert" className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="h-11 w-full rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink transition hover:brightness-95 disabled:opacity-50"
        >
          {loading ? "Подождите…" : "Сохранить пароль"}
        </button>
      </form>
    </>
  );
}
