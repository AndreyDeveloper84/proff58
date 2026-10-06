import type React from "react";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import localFont from "next/font/local";
import { AuthStateProvider } from "@/components/auth/AuthStateProvider";
import { CartProvider } from "@/components/cart/CartProvider";
import { WishlistProvider } from "@/components/wishlist/WishlistProvider";
import { Header } from "@/components/layout/Header";
import { ToastRegion } from "@/components/ui/ToastRegion";
import { CookieConsent } from "@/components/layout/CookieConsent";
import { YandexMetrika } from "@/components/analytics/YandexMetrika";
import { CONSENT_COOKIE, parseConsent } from "@/lib/cookie-consent";
import { QuickViewProvider } from "@/components/quickview/QuickViewProvider";
import { Footer } from "@/components/layout/Footer";
import { THEME_INIT_SCRIPT } from "@/components/layout/ThemeToggle";
import { authStateFromCookies } from "@/lib/auth-state";
import { getInfoPageLinks } from "@/lib/info-pages";
import { getSiteTheme } from "@/lib/theme";
import { siteOrigin } from "@/lib/seo";
import { resolveStorefront } from "@/lib/site";
import { StorefrontProvider } from "@/components/site/StorefrontProvider";
import "./globals.css";

// Body / UI — Inter; display (заголовки/цена/спек-статы) — узкий Oswald.
//
// Файлы шрифтов лежат в репозитории (app/fonts), а не тянутся через
// next/font/google: тот на каждой сборке ходил на fonts.googleapis.com, и сбой
// сети ронял выкат (DRF-2734). Что в файлах и как их пересобрать — app/fonts/README.md.
const inter = localFont({
  src: "./fonts/inter-var.woff2",
  weight: "100 900",
  style: "normal",
  variable: "--font-inter",
  display: "swap",
});

// Диапазон начинается с 500, хотя ось файла — с 400: раньше сайту отдавались
// начертания 500–700, и обычная жирность в Oswald рисовалась как 500.
const oswald = localFont({
  src: "./fonts/oswald-var.woff2",
  weight: "500 700",
  style: "normal",
  variable: "--font-oswald",
  display: "swap",
});

const DESCRIPTION = "Профессиональный инструмент и оборудование: каталог, наличие, цены.";

// metadataBase нужен, чтобы og:image ушёл абсолютным URL — мессенджеры и соцсети
// относительный путь не разворачивают и превью не покажут. Сама картинка
// подхватывается по файловому соглашению из app/opengraph-image.png.
// Функция, а не константа: адрес сайта читается в рантайме (SITE_URL), как у robots и
// sitemap, — иначе canonical и og:url остались бы на домене, вшитом при сборке.
export function generateMetadata(): Metadata {
  const origin = siteOrigin();
  return {
    metadataBase: new URL(origin),
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
      url: origin,
    },
    twitter: { card: "summary_large_image" },
    // PF-SH-RELEASE-01: по умолчанию страницы НЕ индексируются (каталог в работе), ссылки
    // обходятся. index открывают только карточки товаров из allowlist (productSeoMetadata в
    // app/product/[slug]/page.tsx). Переключатель обхода среды — app/robots.ts (lib/seo.ts).
    robots: { index: false, follow: true },
  };
}

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
  // Согласие на cookie читаем здесь же: баннер и скрипт Метрики решаются уже в
  // серверной разметке — у согласившегося ничего не мигает (DRF-2796/2795).
  const consent = parseConsent(cookieStore.get(CONSENT_COOKIE)?.value);
  // Номер счётчика — переменная окружения сервера (не NEXT_PUBLIC_: подставляется в
  // рантайме, а не при сборке образа). Пусто или не число — Метрики на сайте нет.
  const metrikaRaw = (process.env.YANDEX_METRIKA_ID ?? "").trim();
  const metrikaId = /^\d+$/.test(metrikaRaw) ? Number(metrikaRaw) : NaN;

  // Тема: светлая по макету (#477) — она же серверный рендер. Реальную тему
  // посетителя (сохранённый выбор, иначе светлая — UX-01) ставит THEME_INIT_SCRIPT в
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
        <StorefrontProvider value={storefront}>
        <AuthStateProvider state={authState}>
          <CartProvider>
            <WishlistProvider>
              {/* UX-05: быстрый просмотр товара — внутри корзины и избранного, потому что
                  окно пользуется обоими. */}
              <QuickViewProvider>
                <div className="flex min-h-screen flex-col">
                  <Header
                    logoUrl={theme.logo_url}
                    siteName={theme.name}
                    storefront={storefront}
                    infoPages={infoPages}
                  />
                  <div className="flex-1">{children}</div>
                  <Footer
                    logoUrl={theme.logo_url}
                    siteName={theme.name}
                    storefront={storefront}
                    infoPages={infoPages}
                  />
                </div>
              </QuickViewProvider>
              <CookieConsent initialConsent={consent} />
              {Number.isFinite(metrikaId) && metrikaId > 0 && (
                <YandexMetrika counterId={metrikaId} initialConsent={consent} />
              )}
              {/* Единый регион всплывающих уведомлений: «скопировано» (UX-03), корзина и т. п. */}
              <ToastRegion />
            </WishlistProvider>
          </CartProvider>
        </AuthStateProvider>
        </StorefrontProvider>
      </body>
    </html>
  );
}
