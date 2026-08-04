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
    <main className="mx-auto w-full max-w-[1440px] px-4 py-5 sm:px-6 sm:py-7 lg:px-8 lg:py-9">
      <nav aria-label="Хлебные крошки" className="mb-3 flex items-center gap-1 text-xs text-ink-3">
        <Link href="/" className="hover:text-accent">
          Главная
        </Link>
        <span aria-hidden>/</span>
        <span className="text-ink-2">Сравнение</span>
      </nav>

      <div className="mb-5 sm:mb-7">
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink md:text-4xl">
          Сравнение товаров
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-2 sm:text-base">
          Сопоставьте характеристики, цены и наличие — всё важное собрано в одной таблице.
        </p>
      </div>

      <CompareTable />
    </main>
  );
}
