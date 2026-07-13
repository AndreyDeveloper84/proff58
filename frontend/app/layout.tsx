import type React from "react";
import type { Metadata } from "next";
import { Inter, Oswald } from "next/font/google";
import { CartProvider } from "@/components/cart/CartProvider";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { getSiteTheme } from "@/lib/theme";
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

  // #477: светлая тема — по умолчанию (токены в :root). Тёмная — под классом .dark
  // (secondary/dark-mode). Шапка/подвал остаются тёмными: класс dark на их корне
  // (см. Header/Footer). Витрина товарных поверхностей — светлая.
  return (
    <html
      lang="ru"
      className={`${inter.variable} ${oswald.variable} h-full`}
      style={
        {
          "--primary": theme.primary_color,
          "--accent": theme.accent_color,
        } as React.CSSProperties
      }
    >
      <body className="min-h-full antialiased">
        {/* CartProvider — общее состояние корзины (счётчик Header, add-to-cart). */}
        <CartProvider>
          <div className="flex min-h-screen flex-col">
            <Header logoUrl={theme.logo_url} siteName={theme.name} />
            <div className="flex-1">{children}</div>
            <Footer />
          </div>
        </CartProvider>
      </body>
    </html>
  );
}
