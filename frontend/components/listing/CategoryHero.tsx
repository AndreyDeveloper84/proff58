import { Wrench } from "lucide-react";
import { pluralize } from "@/lib/format";

// Hero-баннер категории (PLP) — по утверждённому макету (photo_9): светлая карточка
// с рамкой, слева вертикальная зелёная тех-линия, крупный заголовок + зелёный счётчик
// товаров + описание, справа — крупный blueprint-контур инструмента (фирменный акцент).
// Единственный <h1> страницы. total (опц.) — счётчик найденных товаров.

type Hero = {
  image: string | null;
  eyebrow: string;
};

export function CategoryHero({
  title,
  intro,
  hero,
  total,
}: {
  title: string;
  intro?: string;
  hero?: Hero;
  total?: number;
}) {
  return (
    <section className="relative mb-6 overflow-hidden rounded-xl border border-line bg-surface">
      {hero?.image && (
        // Опциональный фон-фото (если задан в категории) поверх светлой карточки.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={hero.image} alt="" className="absolute inset-0 h-full w-full object-cover opacity-15" />
      )}

      {/* Технический blueprint-чертёж справа (фирменный акцент, как в макете photo_9). */}
      <svg
        aria-hidden
        viewBox="0 0 600 260"
        className="pointer-events-none absolute right-0 top-0 hidden h-full w-1/2 text-ink-3/30 lg:block"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
      >
        {/* оси/размерные линии */}
        <path d="M60 130 H540 M150 50 H470 M150 210 H470" />
        {/* корпус инструмента */}
        <rect x="180" y="80" width="240" height="100" rx="14" />
        <circle cx="150" cy="130" r="30" />
        <circle cx="150" cy="130" r="10" />
        {/* патрон/насадка */}
        <path d="M420 108 h70 l26 22 -26 22 h-70 z" />
        {/* засечки размеров */}
        <path d="M150 44 v12 M470 44 v12 M150 204 v12 M470 204 v12" />
      </svg>

      <div className="relative z-10 flex gap-5 p-6 md:p-8">
        {/* Вертикальная зелёная тех-линия слева с засечками. */}
        <div className="relative hidden w-4 shrink-0 md:block" aria-hidden>
          <span className="absolute left-1.5 top-1 bottom-1 w-px bg-accent/50" />
          <span className="absolute left-1 top-0 h-2 w-2 rounded-full border-2 border-accent bg-surface" />
          <span className="absolute left-0.5 bottom-0 flex flex-col gap-0.5">
            <span className="h-px w-2.5 bg-accent/60" />
            <span className="h-px w-2 bg-accent/60" />
            <span className="h-px w-2.5 bg-accent/60" />
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-4">
            <Wrench
              aria-hidden
              strokeWidth={1.25}
              className="mt-1 hidden h-12 w-12 shrink-0 text-ink-2 sm:block"
            />
            <div className="min-w-0">
              <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
                <h1 className="font-display text-3xl font-bold text-ink md:text-4xl">{title}</h1>
                {total != null && total > 0 && (
                  <span className="pb-1 text-sm font-semibold text-accent">
                    {total} {pluralize(total, "товар", "товара", "товаров")}
                  </span>
                )}
              </div>
              {intro && (
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-2 md:text-base">
                  {intro}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
