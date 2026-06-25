import type { CompatibilitySections as Sections } from "@/lib/types";
import { ProductCard } from "./ProductCard";

const TITLES: Record<keyof Sections, string> = {
  accessories: "Аксессуары и расходники",
  fits: "Подходит к",
  compatible: "Совместимые товары",
};

// Секции совместимости на PDP. Пустые секции не рендерим; вообще нет данных → ничего.
export function CompatibilitySections({ sections }: { sections?: Sections }) {
  if (!sections) return null;
  const order: (keyof Sections)[] = ["accessories", "fits", "compatible"];
  const nonEmpty = order.filter((k) => sections[k].length > 0);
  if (!nonEmpty.length) return null;

  return (
    <div className="flex flex-col gap-8">
      {nonEmpty.map((key) => (
        <section key={key} aria-label={TITLES[key]}>
          <h2 className="mb-3 font-display text-lg font-semibold text-ink">{TITLES[key]}</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {sections[key].map((p) => (
              <ProductCard key={p.id} product={p} view="grid" />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
