import type { Metadata } from "next";
import { Inter, Oswald } from "next/font/google";
import { CartProvider } from "@/components/cart/CartProvider";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
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

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // dark — тёмная тема по умолчанию (дизайн dark-only); токены в :root.
  return (
    <html lang="ru" className={`dark ${inter.variable} ${oswald.variable} h-full`}>
      <body className="min-h-full antialiased">
        {/* CartProvider — общее состояние корзины (счётчик Header, add-to-cart). */}
        <CartProvider>
          <div className="flex min-h-screen flex-col">
            <Header />
            <div className="flex-1">{children}</div>
            <Footer />
          </div>
        </CartProvider>
      </body>
    </html>
  );
}
