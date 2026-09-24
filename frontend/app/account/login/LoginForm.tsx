"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Building2, Eye, EyeOff, Hash, LockKeyhole, Mail, User } from "lucide-react";
import { login, register } from "@/lib/auth";
import { safeNextPath } from "@/lib/auth-state";
import { oauthErrorMessage, type OAuthProviderId } from "@/lib/oauth";
import { MaxAuthFlow } from "@/components/account/MaxAuthFlow";
import { OAuthButtons } from "@/components/account/OAuthButtons";
import { isValidInn, isValidKpp, isLegalEntityInn } from "@/lib/validation";

// Куда вернуть после входа (§16.7): ?next=<path> из URL, иначе профиль.
function nextTarget(): string {
  if (typeof window === "undefined") return "/account/profile";
  return safeNextPath(new URLSearchParams(window.location.search).get("next")) ?? "/account/profile";
}

type CustomerType = "b2c" | "b2b";

const INPUT_CLASS =
  "h-11 w-full rounded-md border border-line bg-field pl-10 pr-3 text-base text-ink outline-none transition placeholder:text-ink-3 focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

/**
 * Поле формы в стиле макета: без видимой подписи (она есть для читалок —
 * sr-only label), иконка слева внутри поля, подсказка по смыслу — placeholder.
 */
function IconField({
  id,
  label,
  icon: Icon,
  hint,
  trailing,
  children,
}: {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  hint?: string;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <div className="relative">
        <Icon
          className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-3"
          aria-hidden
        />
        {children}
        {trailing}
      </div>
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-ink-3">
          {hint}
        </p>
      )}
    </div>
  );
}

function Divider({ children }: { children: ReactNode }) {
  return (
    <div className="my-5 flex items-center gap-3 text-sm text-ink-3">
      <span className="h-px flex-1 bg-line" aria-hidden />
      {children}
      <span className="h-px flex-1 bg-line" aria-hidden />
    </div>
  );
}

export function LoginForm({
  providers,
  next,
  oauthError,
  oauthProvider,
}: {
  /** Включённые провайдеры (SSR); пусто — соцблока нет вовсе. */
  providers: OAuthProviderId[];
  /** Проверенный ?next= для ссылок старта у провайдеров; null — не передаём. */
  next: string | null;
  /** ?oauth_error= после неудачного входа у провайдера. */
  oauthError?: string | null;
  oauthProvider?: string | null;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [name, setName] = useState("");
  // Кто регистрируется. Организация указывает реквизиты сразу: с ними кабинет
  // сразу «свой» — со счетами и карточкой компании.
  const [customerType, setCustomerType] = useState<CustomerType>("b2c");
  const [companyName, setCompanyName] = useState("");
  const [inn, setInn] = useState("");
  const [kpp, setKpp] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // Текст фиксируем при первом рендере: после очистки адреса сервер отдаст
  // страницу уже без oauth_error, а сообщение должно остаться на экране.
  const [oauthMessage] = useState(() => (oauthError ? oauthErrorMessage(oauthError, oauthProvider) : ""));

  const isCompany = customerType === "b2b";

  // Код ошибки показан — убираем его из адреса, чтобы обновление страницы или
  // ссылка, скопированная из строки, не показывали ошибку заново. next и прочее
  // оставляем: после входа человек должен попасть туда, куда шёл.
  useEffect(() => {
    if (!oauthError) return;
    const params = new URLSearchParams(window.location.search);
    params.delete("oauth_error");
    params.delete("provider");
    const query = params.toString();
    router.replace(`${window.location.pathname}${query ? `?${query}` : ""}`, { scroll: false });
  }, [oauthError, router]);

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

  const hasProviders = providers.length > 0;
  const kppRequired = isLegalEntityInn(inn);

  return (
    <section className="rounded-lg border border-line bg-card p-6 shadow-card sm:p-8">
      <h1 className="text-3xl font-bold text-ink">
        {mode === "login" ? "Вход в личный кабинет" : "Регистрация"}
      </h1>
      <p className="mt-2 text-sm text-ink-3">
        Проверяйте заказы, счета и уведомления в одном месте.
      </p>

      <div className="mt-6">
        <MaxAuthFlow mode="login" onCompleted={() => router.push(nextTarget())} />
        <p className="mt-2 text-center text-xs text-ink-3">
          Без пароля — подтвердите вход в приложении
        </p>
      </div>

      {hasProviders ? (
        <>
          <Divider>
            {mode === "login" ? "или войдите через" : "или зарегистрируйтесь через"}
          </Divider>
          <OAuthButtons providers={providers} next={next} />
          <p className="mt-3 text-center text-xs text-ink-3">
            Продолжая, вы соглашаетесь на обработку персональных данных.
          </p>
          <Divider>или по e-mail</Divider>
        </>
      ) : (
        <Divider>или</Divider>
      )}

      {oauthMessage && (
        <p
          role="alert"
          className="mb-4 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          {oauthMessage}
        </p>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {mode === "register" && (
          <IconField id="login-name" label="Имя" icon={User}>
            <input
              id="login-name"
              type="text"
              placeholder="Имя"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={INPUT_CLASS}
              autoComplete="name"
            />
          </IconField>
        )}

        <IconField id="login-email" label="E-mail" icon={Mail}>
          <input
            id="login-email"
            type="email"
            placeholder="E-mail"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={INPUT_CLASS}
            required
            autoComplete="email"
          />
        </IconField>

        <IconField
          id="login-password"
          label="Пароль"
          icon={LockKeyhole}
          trailing={
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
              aria-pressed={showPassword}
              className="absolute right-1 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-md text-ink-3 transition hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {showPassword ? (
                <EyeOff className="h-5 w-5" aria-hidden />
              ) : (
                <Eye className="h-5 w-5" aria-hidden />
              )}
            </button>
          }
        >
          <input
            id="login-password"
            type={showPassword ? "text" : "password"}
            placeholder="Пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={`${INPUT_CLASS} pr-11`}
            required
            autoComplete={mode === "register" ? "new-password" : "current-password"}
          />
        </IconField>

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
                    className={`flex min-h-11 cursor-pointer items-center justify-center rounded-md border px-3 text-sm font-medium transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent ${
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
                <IconField id="login-company" label="Название организации" icon={Building2}>
                  <input
                    id="login-company"
                    type="text"
                    placeholder="Название организации"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    className={INPUT_CLASS}
                    required
                    autoComplete="organization"
                  />
                </IconField>
                <IconField
                  id="login-inn"
                  label="ИНН"
                  icon={Hash}
                  hint="10 цифр — организация, 12 — ИП."
                >
                  <input
                    id="login-inn"
                    type="text"
                    inputMode="numeric"
                    placeholder="ИНН"
                    value={inn}
                    onChange={(e) => setInn(e.target.value)}
                    className={INPUT_CLASS}
                    required
                    aria-describedby="login-inn-hint"
                  />
                </IconField>
                <IconField
                  id="login-kpp"
                  label="КПП"
                  icon={Hash}
                  hint={
                    kppRequired
                      ? "9 цифр, обязателен для организации."
                      : "9 цифр. У ИП его нет — оставьте пустым."
                  }
                >
                  <input
                    id="login-kpp"
                    type="text"
                    inputMode="numeric"
                    placeholder="КПП"
                    value={kpp}
                    onChange={(e) => setKpp(e.target.value)}
                    className={INPUT_CLASS}
                    required={kppRequired}
                    aria-describedby="login-kpp-hint"
                  />
                </IconField>
              </div>
            )}
          </>
        )}

        {error && (
          <p className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="h-11 w-full rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink transition hover:brightness-95 disabled:opacity-50"
        >
          {loading ? "Подождите…" : mode === "register" ? "Зарегистрироваться" : "Войти"}
        </button>
      </form>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-sm">
        {mode === "register" ? (
          <p>
            <span className="text-ink-3">Уже есть аккаунт?</span>{" "}
            <button
              type="button"
              onClick={() => setMode("login")}
              className="font-medium text-accent hover:underline"
            >
              Войти
            </button>
          </p>
        ) : (
          <p>
            <span className="text-ink-3">Нет аккаунта?</span>{" "}
            <button
              type="button"
              onClick={() => setMode("register")}
              className="font-medium text-accent hover:underline"
            >
              Зарегистрироваться
            </button>
          </p>
        )}
        {mode === "login" && (
          <Link href="/account/forgot-password" className="font-medium text-accent hover:underline">
            Забыли пароль?
          </Link>
        )}
      </div>
    </section>
  );
}
