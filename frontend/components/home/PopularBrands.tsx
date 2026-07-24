import Link from "next/link";
import { HOME_CONTENT } from "@/lib/home-content";

// #589: «Популярные бренды» — ряд карточек по макету. Логотипов-ассетов пока
// нет: текстовые «лого» (display-шрифт), структура карточки позволит заменить
// на изображения без правки раскладки. Ссылка — поиск по бренду (маршрута
// «все товары бренда» нет; /search?q= — рабочий и не битый).
export function PopularBrands() {
  const brands = HOME_CONTENT.popularBrands;
  if (!brands.length) return null;

  return (
    <section className="bg-canvas" aria-labelledby="popular-brands-title">
      <div className="mx-auto max-w-[1400px] px-4 pb-10 lg:pb-12">
        <h2
          id="popular-brands-title"
          className="mb-4 font-display text-xl font-bold text-ink sm:text-2xl"
        >
          Популярные бренды
        </h2>
        <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-5 lg:grid-cols-9">
          {brands.map((brand) => (
            <Link
              key={brand}
              href={`/search?q=${encodeURIComponent(brand)}`}
              aria-label={`Товары бренда ${brand}`}
              className="group grid h-14 place-items-center rounded-md border border-line bg-surface px-2 transition hover:border-accent"
            >
              <span className="select-none font-display text-sm font-bold uppercase tracking-wide text-ink-2 transition group-hover:text-ink sm:text-base">
                {brand}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
