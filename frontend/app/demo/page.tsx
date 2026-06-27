import { ProductCard } from "@/components/product/ProductCard";
import type { Product } from "@/lib/types";

// Демо-данные для проверки карточки во всех состояниях (Commit 2).
// Реальные данные приедут из фикстуры/API на следующих этапах.
const base: Product = {
  id: 1,
  slug: "bosch-gbh-2-26",
  name: "Перфоратор Bosch GBH 2-26 DRE SDS-Plus",
  brand: "Bosch",
  image: "/sample-tool.svg",
  rating: 4.7,
  reviews: 128,
  specs: [
    { label: "Мощность", value: "800 Вт" },
    { label: "Энергия", value: "2.7 Дж" },
    { label: "Патрон", value: "SDS-Plus" },
  ],
  energy: "2.7 Дж",
  price: { final: 12990, old: 15490, discountPct: 16, currency: "RUB" },
  stock: "in",
  badges: ["hit", "sale"],
};

const states: { title: string; product: Product }[] = [
  { title: "В наличии · скидка · хит", product: base },
  {
    title: "Под заказ · новинка",
    product: {
      ...base,
      id: 2,
      slug: "makita-hr2470",
      name: "Перфоратор Makita HR2470 SDS-Plus",
      brand: "Makita",
      price: { final: 10490, currency: "RUB" },
      stock: "order",
      badges: ["new"],
      energy: "2.4 Дж",
      rating: 4.5,
      reviews: 64,
    },
  },
  {
    title: "Нет в наличии",
    product: { ...base, id: 3, slug: "dewalt-d25133", name: "Перфоратор DeWalt D25133K", brand: "DeWalt", stock: "out", badges: [], price: { final: 13990, currency: "RUB" } },
  },
  {
    title: "Без фото",
    product: { ...base, id: 4, slug: "p4", image: undefined, badges: [], rating: undefined, reviews: undefined },
  },
  {
    title: "Цена по запросу",
    product: { ...base, id: 5, slug: "p5", price: { currency: "RUB" }, badges: [], stock: "order" },
  },
  {
    title: "Без рейтинга / спеков",
    product: { ...base, id: 6, slug: "p6", rating: undefined, reviews: undefined, specs: [], energy: undefined, badges: [] },
  },
];

export default function DemoPage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <h1 className="mb-1 font-display text-3xl font-semibold uppercase tracking-wide text-ink">
        ProductCard
      </h1>
      <p className="mb-8 text-sm text-ink-3">
        Демо состояний карточки (Commit 2). Сетка — вид grid; ниже — вид list.
      </p>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {states.map(({ title, product }) => (
          <div key={product.id} className="flex flex-col gap-2">
            <span className="text-[11px] uppercase tracking-wide text-ink-3">{title}</span>
            <ProductCard product={product} />
          </div>
        ))}
      </div>

      <h2 className="mb-3 mt-12 font-display text-xl font-semibold uppercase tracking-wide text-ink">
        Вид «список»
      </h2>
      <div className="flex flex-col gap-3">
        <ProductCard product={base} view="list" />
        <ProductCard product={states[1].product} view="list" />
      </div>
    </main>
  );
}
