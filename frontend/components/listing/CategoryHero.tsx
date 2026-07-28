import Image from "next/image";
import { Wrench } from "lucide-react";

import { categorySkeleton } from "@/lib/category-artwork";
import { pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

// Hero-баннер категории (PLP). Режимы:
//   card   — отдельная карточка с рамкой, тех-линией и иконкой (самостоятельный блок);
//   inline — без внешней карточки и левого отступа: H1/описание встают на одну
//            вертикальную линию с тулбаром и сеткой товаров (правая колонка PLP).
// Справа в обоих режимах — контурный чертёж раздела (lib/category-artwork).
// Единственный <h1> страницы.

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
  /** Названия вышестоящих разделов — запасной чертёж для подкатегорий. */
  parentTitles?: string[];
};

export function CategoryHero({
  title,
  intro,
  hero,
  total,
  variant = "card",
  className,
  parentTitles = [],
}: CategoryHeroProps) {
  const inline = variant === "inline";
  // Свой чертёж есть не у каждой подкатегории: «Домкраты» берут чертёж
  // «Автоинструмента» — это лучше, чем пустое место справа от заголовка.
  const skeleton =
    categorySkeleton(title) ??
    parentTitles.map((parent) => categorySkeleton(parent)).find(Boolean) ??
    null;

  return (
    <section
      className={cn(
        "relative overflow-hidden",
        // Высоту резервируем только там, где виден чертёж (lg+): на мобильном она
        // обернулась бы пустой полосой между заголовком и разделами.
        inline ? "lg:min-h-[156px]" : "mb-6 rounded-xl border border-line bg-surface",
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

      {/* Чертёж раздела справа от заголовка — вместо прежней абстрактной
          заглушки. Для незнакомого раздела чертежа нет, и блок просто остаётся
          без иллюстрации. На узких экранах прячем: места под него нет. */}
      {skeleton && (
        <Image
          src={skeleton}
          alt=""
          width={600}
          height={260}
          unoptimized
          priority
          aria-hidden
          className={cn(
            "pointer-events-none absolute right-3 top-1/2 hidden w-auto max-w-[52%] -translate-y-1/2 object-contain lg:block",
            inline ? "h-[96%]" : "h-[86%]",
          )}
        />
      )}

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
                    {total.toLocaleString("ru-RU")} {pluralize(total, "товар", "товара", "товаров")}
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
