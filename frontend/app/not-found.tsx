import Link from "next/link";
import type { Metadata } from "next";
import { SearchX } from "lucide-react";

import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Страница не найдена — Профессионал",
  robots: { index: false, follow: true },
};

// Раньше на несуществующем адресе показывалась стандартная заглушка Next.js —
// «404 This page could not be found» по-английски, посреди пустого экрана, без
// единой ссылки. Человек, попавший сюда по старой ссылке или опечатке, упирался
// в тупик. Здесь тот же тупик превращён в развилку: поиск и живые разделы.
export default function NotFound() {
  return (
    <main className="mx-auto w-full max-w-[1400px] px-4 py-12 lg:py-20">
      <div className="mx-auto max-w-2xl text-center">
        <SearchX className="mx-auto h-12 w-12 text-ink-3" strokeWidth={1.25} aria-hidden />
        <p className="mt-4 font-display text-5xl font-bold text-ink">404</p>
        <h1 className="mt-2 font-display text-2xl font-bold text-ink md:text-3xl">
          Такой страницы нет
        </h1>
        <p className="mt-3 text-ink-2">
          Возможно, товар снят с продажи, раздел переехал или в адресе опечатка.
          Найдём нужное через поиск или каталог.
        </p>

        {/* Обычная форма, а не клиентский компонент: страница ошибки обязана
            работать даже если что-то пошло не так со скриптами. */}
        <form action="/search" method="get" className="mx-auto mt-6 flex max-w-md gap-2">
          <label htmlFor="notfound-search" className="sr-only">
            Поиск по каталогу
          </label>
          <input
            id="notfound-search"
            name="q"
            type="search"
            placeholder={SITE.header.searchPlaceholder}
            className="h-11 min-w-0 flex-1 rounded-md border border-line bg-surface px-3 text-sm text-ink"
          />
          <button
            type="submit"
            className="h-11 shrink-0 rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink transition hover:brightness-95"
          >
            Найти
          </button>
        </form>

        <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/catalog"
            className="inline-flex h-11 items-center rounded-md border border-line px-4 text-sm font-medium text-ink-2 transition hover:border-accent hover:text-accent"
          >
            Каталог товаров
          </Link>
          <Link
            href="/"
            className="inline-flex h-11 items-center rounded-md border border-line px-4 text-sm font-medium text-ink-2 transition hover:border-accent hover:text-accent"
          >
            На главную
          </Link>
          <a
            href={SITE.phone.href}
            className="inline-flex h-11 items-center rounded-md border border-line px-4 text-sm font-medium text-ink-2 transition hover:border-accent hover:text-accent"
          >
            {SITE.phone.display}
          </a>
        </div>
      </div>
    </main>
  );
}
