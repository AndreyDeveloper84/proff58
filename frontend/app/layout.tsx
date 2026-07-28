import type React from "react";
import type { Metadata } from "next";
import { Inter, Oswald } from "next/font/google";
import { CartProvider } from "@/components/cart/CartProvider";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { THEME_INIT_SCRIPT } from "@/components/layout/ThemeToggle";
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

export const metadata: Metadata = {
  title: {
    default: "Профессионал — территория инструмента",
    template: "%s — Профессионал",
  },
  description:
    "Профессиональный инструмент и оборудование: каталог, наличие, цены.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const theme = await getSiteTheme();
  const storefront = resolveStorefront(theme);

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
        {/* CartProvider — общее состояние корзины (счётчик Header, add-to-cart). */}
        <CartProvider>
          <div className="flex min-h-screen flex-col">
            <Header logoUrl={theme.logo_url} siteName={theme.name} storefront={storefront} />
            <div className="flex-1">{children}</div>
            <Footer logoUrl={theme.logo_url} siteName={theme.name} storefront={storefront} />
          </div>
        </CartProvider>
      </body>
    </html>
  );
}
