import Link from "next/link";
import { HOME_CONTENT } from "@/lib/home-content";
import { cn } from "@/lib/utils";

const BRAND_STYLES: Record<string, string> = {
  Makita: "font-black italic tracking-[-0.06em] text-[#173c48]",
  Bosch: "font-black tracking-[-0.04em] text-[#e1262f]",
  DeWALT: "font-black tracking-[-0.06em] text-[#111] [text-shadow:2px_0_0_#ffd400]",
  Metabo: "font-black tracking-[-0.06em] text-[#264f45]",
  AEG: "font-black tracking-[-0.05em] text-[#111]",
  Milwaukee: "font-bold italic tracking-[-0.08em] text-[#e32329]",
  Hilti: "font-black tracking-[-0.03em] text-[#df2c2c]",
  Stanley: "font-black tracking-[-0.03em] text-[#111]",
  Ресанта: "font-black tracking-[-0.05em] text-[#e12d2d]",
};

// Отдельного backend-маршрута бренда нет, поэтому рабочий путь остаётся
// поиском. Визуальный wordmark не выдаётся за официальный растровый логотип.
export function PopularBrands() {
  const brands = HOME_CONTENT.popularBrands;
  if (!brands.length) return null;

  return (
    <section className="bg-surface" aria-labelledby="popular-brands-title">
      <div className="mx-auto max-w-[1400px] px-4 pt-1.5">
        <h2
          id="popular-brands-title"
          className="mb-2 font-sans text-lg font-bold text-ink"
        >
          Популярные бренды
        </h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-9">
          {brands.map((brand) => (
            <Link
              key={brand}
              href={`/search?q=${encodeURIComponent(brand)}`}
              aria-label={`Товары бренда ${brand}`}
              className="group grid h-10 place-items-center rounded-sm border border-line bg-surface px-2 transition hover:border-accent"
            >
              <span
                className={cn(
                  "select-none font-sans text-sm uppercase transition group-hover:brightness-75",
                  BRAND_STYLES[brand] ?? "font-bold text-ink",
                )}
              >
                {brand}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
