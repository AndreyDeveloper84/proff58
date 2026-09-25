import { getSiteTheme } from "@/lib/theme";
import { LoginForm } from "@/components/account/LoginForm";

// Серверная обёртка: узнаём, настроен ли бот MAX (max_bot_url из SiteSettings/env),
// и не рисуем вход через MAX, если он даст только 503 (T5).
export default async function LoginPage() {
  const theme = await getSiteTheme();
  return <LoginForm maxEnabled={Boolean(theme.max_bot_url)} />;
}
