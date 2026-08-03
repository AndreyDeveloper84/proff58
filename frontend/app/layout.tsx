import type React from "react";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Inter, Oswald } from "next/font/google";
import { AuthStateProvider } from "@/components/auth/AuthStateProvider";
import { CartProvider } from "@/components/cart/CartProvider";
import { WishlistProvider } from "@/components/wishlist/WishlistProvider";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { THEME_INIT_SCRIPT } from "@/components/layout/ThemeToggle";
import { authStateFromCookies } from "@/lib/auth-state";
import { getInfoPageLinks } from "@/lib/info-pages";
import { getSiteTheme } from "@/lib/theme";
import { resolveStorefront } from "@/lib/site";
import "./globals.css";

// Body / UI — Inter; display (заголовки/цена/спек-статы) — узкий Oswald.
const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
  display: "swap",
});

const oswald = Oswald({
  subsets: ["latin", "cyrillic"],
  weight: ["500", "600", "700"],
  variable: "--font-oswald",
  display: "swap",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://proff58.ru";
const DESCRIPTION = "Профессиональный инструмент и оборудование: каталог, наличие, цены.";

// metadataBase нужен, чтобы og:image ушёл абсолютным URL — мессенджеры и соцсети
// относительный путь не разворачивают и превью не покажут. Сама картинка
// подхватывается по файловому соглашению из app/opengraph-image.png.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Профессионал — территория инструмента",
    template: "%s — Профессионал",
  },
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    locale: "ru_RU",
    siteName: "Профессионал",
    title: "Профессионал — территория инструмента",
    description: DESCRIPTION,
    url: SITE_URL,
  },
  twitter: { card: "summary_large_image" },
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Тема и список инфо-страниц — независимые запросы, поэтому параллельно:
  // последовательные добавили бы задержку к КАЖДОЙ странице сайта.
  const [theme, infoPages] = await Promise.all([getSiteTheme(), getInfoPageLinks()]);
  const storefront = resolveStorefront(theme);

  // Вошёл ли посетитель — по cookie, без обращения к Django (см. lib/auth-state).
  // Считаем здесь, потому что сессионная cookie HttpOnly и браузеру не видна, а
  // ссылки шапки должны быть верными уже в серверной разметке.
  const cookieStore = await cookies();
  const authState = authStateFromCookies((name) => cookieStore.has(name));

  // Тема: светлая по макету (#477) — она же серверный рендер. Реальную тему
  // посетителя (сохранённый выбор либо системная) ставит THEME_INIT_SCRIPT в
  // <head> до первой отрисовки, поэтому <html> помечен suppressHydrationWarning:
  // атрибут в DOM к моменту гидрации намеренно отличается от серверного.
  return (
    <html
      lang="ru"
      data-theme="light"
      suppressHydrationWarning
      className={`${inter.variable} ${oswald.variable} h-full`}
      style={
        {
          // Основной бренд-цвет темизируется через SiteSettings; акцент/CTA —
          // фиксированный зелёный из дизайн-системы (globals.css), не из настроек
          // (утверждённый макет — одноцветный зелёный, без лайма).
          "--primary": theme.primary_color,
        } as React.CSSProperties
      }
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full antialiased">
        {/* CartProvider — общее состояние корзины (счётчик Header, add-to-cart);
            WishlistProvider — избранное (сердечки карточек знают друг о друге). */}
        <AuthStateProvider state={authState}>
          <CartProvider>
            <WishlistProvider>
              <div className="flex min-h-screen flex-col">
                <Header logoUrl={theme.logo_url} siteName={theme.name} storefront={storefront} />
                <div className="flex-1">{children}</div>
                <Footer
                  logoUrl={theme.logo_url}
                  siteName={theme.name}
                  storefront={storefront}
                  infoPages={infoPages}
                  authState={authState}
                />
              </div>
            </WishlistProvider>
          </CartProvider>
        </AuthStateProvider>
      </body>
    </html>
  );
}
