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

  // #474: токены темы — по data-theme (light-first база в :root, dark — островами).
  // Текущая витрина остаётся тёмной: data-theme="dark" на корне (класс dark сохранён
  // для существующих dark:-вариантов). Светлые товарные поверхности задаются
  // data-theme="light" на своём поддереве.
  return (
    <html
      lang="ru"
      data-theme="dark"
      className={`dark ${inter.variable} ${oswald.variable} h-full`}
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
