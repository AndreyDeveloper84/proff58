import type { CompatibilitySections as Sections } from "@/lib/types";
import { ProductCard } from "./ProductCard";

const TITLES: Record<keyof Sections, string> = {
  accessories: "Аксессуары и расходники",
  crossSell: "С этим товаром покупают",
  analogs: "Аналоги",
  fits: "Подходит к",
  compatible: "Совместимые товары",
};

// Секции совместимости на PDP. Пустые секции не рендерим; вообще нет данных → ничего.
export function CompatibilitySections({ sections }: { sections?: Sections }) {
  if (!sections) return null;
  // Порядок для покупателя: сначала «докупить», потом «чем заменить», потом справочное.
  const order: (keyof Sections)[] = [
    "accessories",
    "crossSell",
    "analogs",
    "fits",
    "compatible",
  ];
  const nonEmpty = order.filter((k) => sections[k].length > 0);
  if (!nonEmpty.length) return null;

  return (
    <div className="flex flex-col gap-5">
      {nonEmpty.map((key) => (
        // Каждая секция — такой же контейнер, как остальные блоки карточки:
        // раньше они висели голыми заголовками и читались как продолжение
        // страницы, а не как отдельные подборки.
        <section
          key={key}
          aria-label={TITLES[key]}
          className="rounded-lg border border-line bg-surface p-4 sm:p-5"
        >
          <h2 className="mb-3 font-display text-xl font-semibold text-ink">{TITLES[key]}</h2>
          {/* Лента с прокруткой вместо сетки: в секции бывает и три товара, и
              шесть, а сетка на четыре колонки во втором случае переносила
              строку — вторая строка из двух карточек выглядела обрывком. */}
          <div className="grid auto-cols-[minmax(190px,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2 sm:auto-cols-[minmax(210px,1fr)] lg:auto-cols-[minmax(220px,1fr)]">
            {sections[key].map((p) => (
              <ProductCard key={p.id} product={p} variant="home" />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
