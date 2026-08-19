import type { Metadata } from "next";
import { Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { SearchBar } from "@/components/layout/SearchBar";
import { SearchShell } from "@/components/search/SearchShell";
import { searchListing } from "@/lib/catalog";
import { parseQuery } from "@/lib/url-state";

export const metadata: Metadata = { title: "Поиск" };

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const raw = Array.isArray(sp.q) ? sp.q[0] : sp.q;
  const query = (raw ?? "").trim();

  // Фильтры, сортировка и страница живут в том же URL, что и запрос (DRF-1166).
  // parseQuery не привязан к категории — передаём пустую.
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(sp)) {
    if (key === "q" || value == null) continue;
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, v);
  }
  const listingQuery = parseQuery(params, "");
  const listing = query ? await searchListing(query, listingQuery) : null;

  return (
    <main className="mx-auto w-full max-w-[1680px] px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-7">
      <nav
        aria-label="Хлебные крошки"
        className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex"
      >
        <Link href="/" className="hover:text-accent">Главная</Link>
        <span aria-hidden>›</span>
        <span>Поиск</span>
      </nav>

      <h1 className="font-display text-2xl font-semibold text-ink lg:text-[30px]">
        {query ? (
          <>
            Результаты поиска: <span>«{query}»</span>
          </>
        ) : (
          "Поиск"
        )}
      </h1>

      {/* Поле поиска на самой странице. Раньше здесь была надпись «введите
          запрос в строку поиска», а самой строки на странице не было: на телефоне
          её в шапке нет вовсе, и переход из подвала упирался в тупик. */}
      <SearchBar
        className="mt-3 max-w-2xl"
        placeholder="Модель, артикул или бренд"
        initialQuery={query}
      />

      {!query ? (
        <div className="mt-4 rounded-lg border border-line bg-surface p-8 text-center">
          <SearchIcon className="mx-auto h-10 w-10 text-ink-3" strokeWidth={1.5} aria-hidden />
          <p className="mt-3 text-sm text-ink-2">
            Введите модель, артикул или бренд — например, «перфоратор Bosch» или «SDS-plus»
          </p>
          <Link href="/catalog" className="mt-4 inline-block">
            <Button variant="accent">Открыть каталог</Button>
          </Link>
        </div>
      ) : !listing || listing.total === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-lg border border-line bg-surface p-12 text-center">
          <SearchIcon className="h-16 w-16 text-ink-3" strokeWidth={1} aria-hidden />
          <p className="text-lg text-ink-2">По запросу «{query}» ничего не найдено</p>
          <p className="text-sm text-ink-3">Попробуйте изменить запрос или перейдите в каталог</p>
          <Link href="/catalog">
            <Button variant="accent">Перейти в каталог</Button>
          </Link>
        </div>
      ) : (
        <SearchShell listing={listing} query={listingQuery} q={query} />
      )}
      <MobileBottomNav active="search" />
    </main>
  );
}
