import type { Metadata } from "next";
import Link from "next/link";
import { Bell, FileText, Heart, Lock, Package } from "lucide-react";
import { safeNextPath } from "@/lib/auth-state";
import { getLoginOAuthProviders } from "@/lib/oauth-providers";
import { getSiteTheme } from "@/lib/theme";
import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Вход" };

// Страница входа: серверная половина. Здесь — то, что известно до отрисовки:
// какие провайдеры входа включены (SSR-запрос в Django) и параметры адреса.
// Сама форма со всей логикой входа/регистрации/MAX — клиентский LoginForm.
type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

function first(v: string | string[] | undefined): string | null {
  return (Array.isArray(v) ? v[0] : v) ?? null;
}

const BENEFITS = [
  {
    Icon: Package,
    title: "История и статусы заказов",
    text: "Следите за доставкой и получайте уведомления о каждом этапе заказа.",
  },
  {
    Icon: FileText,
    title: "Счета для организаций",
    text: "Скачивайте счета на оплату в одном месте.",
  },
  {
    Icon: Heart,
    title: "Избранные товары",
    text: "Сохраняйте интересные товары и возвращайтесь к ним позже.",
  },
  {
    Icon: Bell,
    title: "Уведомления в MAX",
    text: "Статусы заказов и сообщения о поступлении товара — в приложении MAX.",
  },
];

export default async function LoginPage({ searchParams }: Props) {
  const [sp, providers, theme] = await Promise.all([
    searchParams,
    getLoginOAuthProviders(),
    getSiteTheme(),
  ]);
  // Бот MAX не настроен (max_bot_url пуст) — вход через MAX дал бы только 503:
  // не показываем ни кнопку, ни обещание уведомлений в MAX.
  const maxEnabled = Boolean(theme.max_bot_url);
  const benefits = maxEnabled ? BENEFITS : BENEFITS.filter((b) => b.title !== "Уведомления в MAX");

  return (
    <main className="mx-auto w-full max-w-[1480px] px-4 pb-10 pt-5 sm:px-6 lg:px-8 lg:pt-7">
      <nav aria-label="Хлебные крошки" className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex">
        <Link href="/" className="hover:text-accent">Главная</Link>
        <span aria-hidden>›</span>
        <span>Вход</span>
      </nav>

      <div className="mx-auto grid max-w-[1000px] gap-5 lg:grid-cols-[1.15fr_.85fr]">
        <LoginForm
          providers={providers}
          next={safeNextPath(first(sp.next))}
          oauthError={first(sp.oauth_error)}
          oauthProvider={first(sp.provider)}
          maxEnabled={maxEnabled}
        />

        <aside className="flex flex-col rounded-lg border border-line bg-card p-6 shadow-card sm:p-8">
          <h2 className="text-xl font-semibold text-ink">В личном кабинете удобно</h2>
          <ul className="mt-7 space-y-6">
            {benefits.map(({ Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <Icon className="h-7 w-7 shrink-0 text-ink-2" strokeWidth={1.5} aria-hidden />
                <div>
                  <p className="font-semibold text-ink">{title}</p>
                  <p className="mt-1 text-sm text-ink-3">{text}</p>
                </div>
              </li>
            ))}
          </ul>

          {/* mt-auto прижимает строку к низу, когда карточка вытянута по соседней. */}
          <div className="mt-auto pt-8">
            <p className="flex items-center gap-3 border-t border-line pt-5 text-xs text-ink-3">
              <Lock className="h-5 w-5 shrink-0" aria-hidden />
              Данные передаются по защищённому соединению
            </p>
          </div>
        </aside>
      </div>
    </main>
  );
}
