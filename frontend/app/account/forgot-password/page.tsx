"use client";

import { useState } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { requestPasswordReset } from "@/lib/auth";
import { SuccessState } from "@/components/ui/states";

// Восстановление пароля по e-mail (DRF-2298). Экран после отправки одинаков
// для любого адреса — по нему нельзя понять, есть ли аккаунт. Отдельно
// показываем только сбой транспорта (503) и «слишком часто» (429).
const INPUT =
  "mt-1 h-11 w-full rounded-md border border-line bg-surface px-3 text-ink outline-none focus:border-accent";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await requestPasswordReset(email.trim());
      setSent(true);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 503) {
        setError("Не удалось отправить письмо. Попробуйте позже.");
      } else if (err instanceof ApiError && err.status === 429) {
        setError("Слишком много запросов. Подождите немного и попробуйте снова.");
      } else {
        setError(err instanceof Error ? err.message : "Ошибка");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto w-full max-w-[1480px] px-4 pb-10 pt-5 sm:px-6 lg:px-8 lg:pt-7">
      <nav aria-label="Хлебные крошки" className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex">
        <Link href="/" className="hover:text-accent">Главная</Link>
        <span aria-hidden>›</span>
        <Link href="/account/login" className="hover:text-accent">Вход</Link>
        <span aria-hidden>›</span>
        <span>Восстановление пароля</span>
      </nav>

      <div className="mx-auto max-w-[480px] rounded-lg border border-line bg-surface p-5 sm:p-7">
        {sent ? (
          <SuccessState
            title="Проверьте почту"
            description="Если адрес зарегистрирован, мы отправили письмо со ссылкой. Ссылка действует один час. Если письма нет — загляните в «Спам»."
            action={
              <Link href="/account/login" className="font-medium text-accent hover:underline">
                Вернуться ко входу
              </Link>
            }
          />
        ) : (
          <>
            <h1 className="text-2xl font-semibold text-ink">Восстановление пароля</h1>
            <p className="mt-1 text-sm text-ink-3">
              Укажите e-mail, с которым регистрировались, — пришлём ссылку для нового пароля.
            </p>
            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <label className="block text-sm text-ink-2">
                E-mail
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={INPUT}
                  required
                  autoComplete="email"
                  placeholder="you@company.ru"
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
                {loading ? "Подождите…" : "Отправить письмо"}
              </button>
            </form>
            <p className="mt-5 border-t border-line pt-5 text-xs text-ink-3">
              Регистрировались через MAX и не задавали пароль? Войдите через MAX — пароль ему не
              нужен. <Link href="/account/login" className="text-accent hover:underline">Ко входу</Link>
            </p>
          </>
        )}
      </div>
    </main>
  );
}
