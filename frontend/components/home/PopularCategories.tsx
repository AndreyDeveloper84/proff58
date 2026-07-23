import Link from "next/link";
import { Grip } from "lucide-react";
import type { CategoryNode } from "@/lib/catalog";

// #589: «Популярные категории» — компактные pill-кнопки по макету (вместо крупных
// плиток). Данные — корневые категории из API (живой контракт сохранён); плитки
// CategoryGrid остаются компонентом для других мест.
export function PopularCategories({ categories }: { categories: CategoryNode[] }) {
  const items = categories.slice(0, 7);
  if (!items.length) return null;

  return (
    <section className="bg-canvas" aria-labelledby="popular-categories-title">
      <div className="mx-auto max-w-[1400px] px-4 pb-8 lg:pb-10">
        <h2
          id="popular-categories-title"
          className="mb-4 font-display text-xl font-bold text-ink sm:text-2xl"
        >
          Популярные категории
        </h2>
        <div className="flex flex-wrap gap-2.5">
          {items.map((cat) => (
            <Link
              key={cat.id}
              href={`/catalog/${cat.slug}`}
              className="inline-flex h-11 items-center rounded-md border border-line bg-surface px-4 text-sm font-medium text-ink transition hover:border-accent hover:text-accent"
            >
              {cat.name}
            </Link>
          ))}
          <Link
            href="/catalog"
            className="inline-flex h-11 items-center gap-2 rounded-md border border-line bg-surface px-4 text-sm font-medium text-ink-2 transition hover:border-accent hover:text-accent"
          >
            <Grip className="h-4 w-4" aria-hidden />
            Ещё категории
          </Link>
        </div>
      </div>
    </section>
  );
}
