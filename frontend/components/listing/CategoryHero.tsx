import { Wrench } from "lucide-react";

import { pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

// Hero-баннер категории (PLP). Режимы:
//   card   — отдельная карточка с рамкой, тех-линией и иконкой (самостоятельный блок);
//   inline — без внешней карточки и левого отступа: H1/описание встают на одну
//            вертикальную линию с тулбаром и сеткой товаров (правая колонка PLP).
// Blueprint-чертёж инструмента справа — в обоих режимах. Единственный <h1> страницы.

type Hero = {
  image: string | null;
  eyebrow: string;
};

type CategoryHeroProps = {
  title: string;
  intro?: string;
  hero?: Hero;
  total?: number;
  variant?: "card" | "inline";
  className?: string;
};

export function CategoryHero({
  title,
  intro,
  hero,
  total,
  variant = "card",
  className,
}: CategoryHeroProps) {
  const inline = variant === "inline";

  return (
    <section
      className={cn(
        "relative overflow-hidden",
        inline ? "min-h-[132px]" : "mb-6 rounded-xl border border-line bg-surface",
        className,
      )}
    >
      {hero?.image && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={hero.image}
          alt=""
          className="absolute inset-0 h-full w-full object-cover opacity-15"
        />
      )}

      <svg
        aria-hidden
        viewBox="0 0 600 260"
        className="pointer-events-none absolute right-0 top-0 hidden h-full w-1/2 text-ink-3/30 lg:block"
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
      >
        <path d="M60 130 H540 M150 50 H470 M150 210 H470" />
        <rect x="180" y="80" width="240" height="100" rx="14" />
        <circle cx="150" cy="130" r="30" />
        <circle cx="150" cy="130" r="10" />
        <path d="M420 108 h70 l26 22 -26 22 h-70 z" />
        <path d="M150 44 v12 M470 44 v12 M150 204 v12 M470 204 v12" />
      </svg>

      <div className={cn("relative z-10 flex", inline ? "py-2 pr-4" : "gap-5 p-6 md:p-8")}>
        {!inline && (
          <div className="relative hidden w-4 shrink-0 md:block" aria-hidden>
            <span className="absolute bottom-1 left-1.5 top-1 w-px bg-accent/50" />
          </div>
        )}

        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-4">
            {!inline && (
              <Wrench
                aria-hidden
                strokeWidth={1.25}
                className="mt-1 hidden h-12 w-12 shrink-0 text-ink-2 sm:block"
              />
            )}

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
