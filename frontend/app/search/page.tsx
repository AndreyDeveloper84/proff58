import type { Metadata } from "next";
import { Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ProductCard } from "@/components/product/ProductCard";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { SearchBar } from "@/components/layout/SearchBar";
import { searchProducts } from "@/lib/catalog";

export const metadata: Metadata = { title: "Поиск" };

// Русское склонение «товар/товара/товаров» по числу найденного.
function plural(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "товар";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "товара";
  return "товаров";
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q = "" } = await searchParams;
  const query = q.trim();
  const products = query ? await searchProducts(query) : [];

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

      {query && products.length > 0 && (
        <p className="mb-5 mt-3 text-sm text-ink-3">
          Найдено {products.length} {plural(products.length)}
        </p>
      )}

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
      ) : products.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-lg border border-line bg-surface p-12 text-center">
          <SearchIcon className="h-16 w-16 text-ink-3" strokeWidth={1} aria-hidden />
          <p className="text-lg text-ink-2">По запросу «{query}» ничего не найдено</p>
          <p className="text-sm text-ink-3">Попробуйте изменить запрос или перейдите в каталог</p>
          <Link href="/catalog">
            <Button variant="accent">Перейти в каталог</Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
      <MobileBottomNav active="search" />
    </main>
  );
}
