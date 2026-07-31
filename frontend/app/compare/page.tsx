import type { Metadata } from "next";
import Link from "next/link";

import { CompareTable } from "./CompareTable";

export const metadata: Metadata = {
  title: "Сравнение товаров — Профессионал",
  // Список выбранного у каждого свой и живёт в браузере — индексировать нечего.
  robots: { index: false, follow: true },
};

export default function ComparePage() {
  return (
    <main className="mx-auto w-full max-w-[1680px] px-4 py-6 sm:px-6 lg:px-8">
      <nav aria-label="Хлебные крошки" className="mb-3 flex items-center gap-1 text-xs text-ink-3">
        <Link href="/" className="hover:text-accent">
          Главная
        </Link>
        <span aria-hidden>/</span>
        <span className="text-ink-2">Сравнение</span>
      </nav>

      <h1 className="mb-4 font-display text-2xl font-bold text-ink md:text-3xl">
        Сравнение товаров
      </h1>

      <CompareTable />
    </main>
  );
}
