"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Bell, ClipboardList, FileText, Heart, ShieldCheck } from "lucide-react";
import { login, register } from "@/lib/auth";
import { MaxAuthFlow } from "@/components/account/MaxAuthFlow";
import { isValidInn, isValidKpp, isLegalEntityInn } from "@/lib/validation";

// Куда вернуть после входа (§16.7): ?next=<path> из URL, иначе профиль.
function nextTarget(): string {
  if (typeof window === "undefined") return "/account/profile";
  const n = new URLSearchParams(window.location.search).get("next");
  return n && n.startsWith("/") ? n : "/account/profile";
}

type CustomerType = "b2c" | "b2b";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  // Кто регистрируется. Организация указывает реквизиты сразу: с ними кабинет
  // сразу «свой» — со счетами и карточкой компании.
  const [customerType, setCustomerType] = useState<CustomerType>("b2c");
  const [companyName, setCompanyName] = useState("");
  const [inn, setInn] = useState("");
  const [kpp, setKpp] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const isCompany = customerType === "b2b";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (mode === "register" && isCompany) {
      // Зеркалит серверную проверку (apps/accounts/requisites.py): человек
      // видит ошибку сразу, а не после ответа.
      if (!companyName.trim()) return setError("Укажите название организации.");
      if (!isValidInn(inn)) return setError("ИНН должен содержать 10 или 12 цифр.");
      if (isLegalEntityInn(inn) && !kpp.trim()) {
        return setError("КПП обязателен для юридического лица (ИНН из 10 цифр).");
      }
      if (kpp.trim() && !isValidKpp(kpp)) return setError("КПП должен содержать 9 цифр.");
    }

    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register({
          email,
          password,
          full_name: name,
          customer_type: customerType,
          ...(isCompany
            ? { company_name: companyName.trim(), inn: inn.trim(), kpp: kpp.trim() }
            : {}),
        });
      }
      // replace: после успешного входа «Назад» не должен возвращать на форму
      // входа — вошедшему она не нужна и выглядит как «меня опять разлогинило».
      router.replace(nextTarget());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="mx-auto w-full max-w-[1480px] px-4 pb-10 pt-5 sm:px-6 lg:px-8 lg:pt-7">
      <nav aria-label="Хлебные крошки" className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex">
        <Link href="/" className="hover:text-accent">Главная</Link>
        <span aria-hidden>›</span>
        <span>Вход</span>
      </nav>

      <div className="mx-auto grid max-w-[920px] overflow-hidden rounded-lg border border-line bg-surface lg:grid-cols-[1.08fr_.92fr]">
        <section className="p-5 sm:p-7 lg:p-8">
          <h1 className="text-2xl font-semibold text-ink">
            {mode === "login" ? "Вход в личный кабинет" : "Регистрация"}
          </h1>
          <p className="mt-1 text-sm text-ink-3">
            Проверяйте заказы, счета и уведомления в одном месте.
          </p>

          <div className="mt-6">
            <MaxAuthFlow mode="login" onCompleted={() => router.push(nextTarget())} />
            <p className="mt-2 text-center text-xs text-ink-3">
              Без пароля — подтвердите вход в приложении
            </p>
            <div className="my-4 flex items-center gap-3 text-xs text-ink-3">
              <span className="h-px flex-1 bg-line" />
              или
              <span className="h-px flex-1 bg-line" />
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && (
              <label className="block text-sm text-ink-2">
                Имя
                <input
                  type="text"
                  placeholder="Алексей Петров"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-1 h-11 w-full rounded-md border border-line bg-surface px-3 text-ink outline-none focus:border-accent"
                />
              </label>
            )}
            <label className="block text-sm text-ink-2">
              E-mail
              <input
                type="email"
                placeholder="you@company.ru"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 h-11 w-full rounded-md border border-line bg-surface px-3 text-ink outline-none focus:border-accent"
                required
                autoComplete="email"
              />
            </label>

            <label className="block text-sm text-ink-2">
              Пароль
              <input
                type="password"
                placeholder="Введите пароль"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 h-11 w-full rounded-md border border-line bg-surface px-3 text-ink outline-none focus:border-accent"
                required
                autoComplete={mode === "register" ? "new-password" : "current-password"}
              />
            </label>

            {mode === "register" && (
              <>
                <fieldset>
                  <legend className="text-sm text-ink-2">Кто покупает</legend>
                  <div className="mt-1 grid grid-cols-2 gap-2">
                    {(
                      [
                        ["b2c", "Частное лицо"],
                        ["b2b", "Организация"],
                      ] as const
                    ).map(([value, label]) => (
                      <label
                        key={value}
                        className={`flex min-h-11 cursor-pointer items-center justify-center rounded-md border px-3 text-sm font-medium transition ${
                          customerType === value
                            ? "border-accent bg-accent/10 text-accent"
                            : "border-line text-ink-2 hover:border-accent/50"
                        }`}
                      >
                        <input
                          type="radio"
                          name="customer-type"
                          value={value}
                          checked={customerType === value}
                          onChange={() => setCustomerType(value)}
                          className="sr-only"
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                </fieldset>

                {isCompany && (
                  <div className="space-y-4 rounded-md border border-line bg-raised p-4">
                    <p className="text-xs text-ink-3">
                      Реквизиты нужны для счёта. Юридический адрес попросим при первом заказе.
                    </p>
                    <label className="block text-sm text-ink-2">
                      Название организации *
                      <input
                        type="text"
                        placeholder="ООО «Профессионал»"
                        value={companyName}
                        onChange={(e) => setCompanyName(e.target.value)}
                        className="mt-1 h-11 w-full rounded-md border border-line bg-surface px-3 text-ink outline-none focus:border-accent"
                        required
                      />
                    </label>
                    <label className="block text-sm text-ink-2">
                      ИНН *
                      <input
                        type="text"
                        inputMode="numeric"
                        placeholder="10 или 12 цифр"
                        value={inn}
                        onChange={(e) => setInn(e.target.value)}
                        className="mt-1 h-11 w-full rounded-md border border-line bg-surface px-3 text-ink outline-none focus:border-accent"
                        required
                      />
                      <span className="mt-1 block text-xs text-ink-3">
                        10 цифр — организация, 12 — ИП.
                      </span>
                    </label>
                    <label className="block text-sm text-ink-2">
                      КПП {isLegalEntityInn(inn) ? "*" : ""}
                      <input
                        type="text"
                        inputMode="numeric"
                        placeholder="9 цифр"
                        value={kpp}
                        onChange={(e) => setKpp(e.target.value)}
                        className="mt-1 h-11 w-full rounded-md border border-line bg-surface px-3 text-ink outline-none focus:border-accent"
                        required={isLegalEntityInn(inn)}
                      />
                      <span className="mt-1 block text-xs text-ink-3">
                        У ИП его нет — оставьте пустым.
                      </span>
                    </label>
                  </div>
                )}
              </>
            )}

            {error && <p className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="h-11 w-full rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink transition hover:brightness-95 disabled:opacity-50"
            >
              {loading ? "Подождите…" : mode === "register" ? "Зарегистрироваться" : "Войти"}
            </button>
          </form>

          <div className="mt-5 space-y-2 border-t border-line pt-5 text-sm">
            {mode === "register" ? (
              <button onClick={() => setMode("login")} className="block font-medium text-accent hover:underline">
                Уже есть аккаунт? Войти
              </button>
            ) : (
              <button onClick={() => setMode("register")} className="block font-medium text-accent hover:underline">
                Нет аккаунта? Зарегистрироваться
              </button>
            )}
            {/* Сброса пароля по письму пока нет — честно указываем рабочий путь. */}
            <p className="text-xs text-ink-3">Забыли пароль? Войдите через MAX — он не требует пароля.</p>
          </div>
        </section>

        <aside className="border-t border-line bg-accent/5 p-5 sm:p-7 lg:border-l lg:border-t-0 lg:p-8">
          <h2 className="text-lg font-semibold text-ink">В личном кабинете удобно</h2>
          <div className="mt-6 space-y-5">
            {[
              [ClipboardList, "История и статусы заказов"],
              [FileText, "Счета для организаций"],
              [Heart, "Избранные товары"],
              [Bell, "Уведомления в MAX"],
            ].map(([Icon, label]) => {
              const FeatureIcon = Icon as typeof ClipboardList;
              return (
                <div key={label as string} className="flex items-center gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface text-accent">
                    <FeatureIcon className="h-5 w-5" aria-hidden />
                  </div>
                  <span className="text-sm font-semibold text-ink">{label as string}</span>
                </div>
              );
            })}
          </div>

          <p className="mt-5 flex items-center gap-2 text-xs text-ink-3">
            <ShieldCheck className="h-5 w-5 text-accent" aria-hidden />
            Данные передаются по защищённому соединению
          </p>
        </aside>
      </div>
    </main>
  );
}
