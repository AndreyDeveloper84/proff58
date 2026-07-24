import Link from "next/link";
import {
  Anvil,
  Drill,
  Gauge,
  Grip,
  Hammer,
  Leaf,
  Ruler,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { CategoryNode } from "@/lib/catalog";

const CATEGORY_ICONS: LucideIcon[] = [Drill, Wrench, Ruler, Leaf, Hammer, Anvil, Gauge];

// Названия, slug и ссылки всегда приходят из backend. Иконки — только
// декоративное оформление позиции в витринном ряду.
export function PopularCategories({ categories }: { categories: CategoryNode[] }) {
  const items = categories.slice(0, 7);
  if (!items.length) return null;

  return (
    <section className="bg-surface" aria-labelledby="popular-categories-title">
      <div className="mx-auto max-w-[1400px] px-4 pt-1.5">
        <h2
          id="popular-categories-title"
          className="mb-2 font-sans text-lg font-bold text-ink"
        >
          Популярные категории
        </h2>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
          {items.map((cat, index) => {
            const Icon = CATEGORY_ICONS[index] ?? Wrench;
            return (
              <Link
                key={cat.id}
                href={`/catalog/${cat.slug}`}
                className="inline-flex min-h-[38px] items-center gap-2 rounded-sm border border-line bg-surface px-3 text-xs font-medium leading-tight text-ink transition hover:border-accent hover:text-accent"
              >
                <Icon className="h-4 w-4 shrink-0 text-ink-2" strokeWidth={1.6} aria-hidden />
                {cat.name}
              </Link>
            );
          })}
          <Link
            href="/catalog"
            className="inline-flex min-h-[38px] items-center justify-center gap-2 rounded-sm border border-line bg-surface px-3 text-xs font-medium text-ink transition hover:border-accent hover:text-accent"
          >
            <Grip className="h-4 w-4" strokeWidth={1.6} aria-hidden />
            Ещё категории
          </Link>
        </div>
      </div>
    </section>
  );
}
