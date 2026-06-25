import type { Metadata } from "next";
import { Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ProductCard } from "@/components/product/ProductCard";
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
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <h1 className="mb-6 font-display text-3xl font-semibold uppercase tracking-wide text-ink">
        {query ? (
          <>
            Результаты поиска: <span className="text-accent">«{query}»</span>
          </>
        ) : (
          "Поиск"
        )}
      </h1>

      {query && products.length > 0 && (
        <p className="mb-4 text-sm text-ink-3">
          Найдено {products.length} {plural(products.length)}
        </p>
      )}

      {!query ? (
        <p className="text-ink-3">Введите запрос в строку поиска</p>
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
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      )}
    </main>
  );
}
