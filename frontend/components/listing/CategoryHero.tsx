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
//
// inline намеренно НЕвысокий: раньше он занимал 280px и вместе с тулбаром съедал
// первый экран — до товаров приходилось прокручивать. Заголовок здесь служебный,
// человек пришёл за выдачей, поэтому высота задаётся содержимым.
//
// `children` — слот под шапкой (капсулы разделов): они часть навигации по
// разделу и стоят рядом с его названием, а не в фильтрах.

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
  /** Навигация по разделу под заголовком (капсулы подкатегорий и типов). */
  children?: React.ReactNode;
};

export function CategoryHero({
  title,
  intro,
  hero,
  total,
  variant = "card",
  className,
  parentTitles = [],
  children,
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
        // В карточном варианте чертёж стоит в собственной grid-колонке.
        !inline && skeleton && "lg:grid lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center lg:gap-6",
        inline
          ? "border-b border-line/80"
          : "mb-6 rounded-xl border border-line bg-surface",
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

      <div
        className={cn(
          "relative z-10 flex lg:col-start-1 lg:row-start-1",
          inline
            ? "flex-col py-4 lg:py-5 lg:pr-[38%]"
            : "gap-5 p-6 md:p-8",
        )}
      >
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
                <h1
                  className={cn(
                    "font-display text-3xl font-bold text-ink md:text-4xl",
                    inline && "text-2xl md:text-[28px] lg:text-[30px] lg:leading-tight",
                  )}
                >
                  {title}
                </h1>

                {total != null && total > 0 && (
                  <span className="pb-1 text-sm font-semibold text-accent">
                    {total.toLocaleString("ru-RU")} {pluralize(total, "товар", "товара", "товаров")}
                  </span>
                )}
              </div>

              {intro && (
                <p
                  className={cn(
                    "mt-2 max-w-2xl text-sm leading-relaxed text-ink-2",
                    // В inline описание — служебная строка над выдачей: держим
                    // её в две строки, иначе шапка снова разрастается.
                    inline ? "line-clamp-2" : "mt-3 md:text-base",
                  )}
                >
                  {intro}
                </p>
              )}
            </div>
          </div>
        </div>

        {children}
      </div>

      {/* В inline-hero все чертежи помещаются в одну и ту же чистую правую
          половину полотна. Поэтому даже широкий перфоратор не пересечёт H1.
          На узких экранах иллюстрацию прячем — места под неё нет. */}
      {skeleton && inline && (
        <div
          className="pointer-events-none absolute inset-y-0 right-0 z-[1] hidden w-1/2 overflow-hidden lg:block"
          aria-hidden
        >
          <Image
            src={skeleton}
            alt=""
            fill
            sizes="50vw"
            unoptimized
            priority
            aria-hidden
            className="object-contain object-right opacity-65 contrast-125 dark:invert dark:opacity-70"
          />
        </div>
      )}

      {skeleton && !inline && (
        <Image
          src={skeleton}
          alt=""
          width={600}
          height={260}
          unoptimized
          priority
          aria-hidden
          className="pointer-events-none hidden h-auto max-h-[190px] w-[420px] max-w-[34vw] justify-self-end object-contain opacity-80 contrast-125 lg:col-start-2 lg:row-start-1 lg:block 2xl:w-[480px] dark:invert dark:opacity-70"
        />
      )}
    </section>
  );
}
