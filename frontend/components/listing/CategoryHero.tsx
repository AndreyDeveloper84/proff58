import { Wrench } from "lucide-react";
import { pluralize } from "@/lib/format";

// Hero-баннер категории (PLP). Презентационный: данные приходят из Listing.category.
// Фон-фото опционально — без него фирменный градиент на токенах темы. Единственный <h1>
// страницы (старый удалён из ListingShell). CTA рендерится только при наличии label+href.
// total (опц.) — счётчик найденных товаров рядом с заголовком; blueprint-контур инструмента
// и вертикальная тех-линия — фирменный акцент из утверждённого макета.

type Hero = {
  image: string | null;
  eyebrow: string;
  ctaLabel: string;
  ctaHref: string;
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
  const hasCta = Boolean(hero?.ctaLabel && hero?.ctaHref);
  return (
    <section className="relative mb-6 overflow-hidden rounded-xl border border-line bg-canvas">
      {hero?.image ? (
        // Декоративный фон → пустой alt.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={hero.image}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div
          aria-hidden
          className="absolute inset-0 bg-[radial-gradient(120%_120%_at_15%_20%,color-mix(in_srgb,var(--accent)_18%,transparent),transparent_55%)]"
        />
      )}
      {/* Затемняющий оверлей для контраста текста (≥ WCAG AA на тёмной теме). */}
      <div className="absolute inset-0 bg-gradient-to-r from-canvas/95 via-canvas/80 to-canvas/40" />

      {/* Blueprint-контур инструмента справа (только без фото-фона, чтобы не спорить). */}
      {!hero?.image && (
        <Wrench
          aria-hidden
          strokeWidth={0.75}
          className="pointer-events-none absolute -right-8 top-1/2 hidden h-72 w-72 -translate-y-1/2 text-ink/[0.05] lg:block"
        />
      )}

      <div className="relative z-10 max-w-2xl px-6 py-12 md:px-10 md:py-16">
        {/* Вертикальная тех-линия слева от заголовка (blueprint-акцент). */}
        <div className="absolute left-0 top-12 hidden h-24 w-px bg-accent/40 md:block" aria-hidden>
          <span className="absolute -left-[3px] top-0 h-1.5 w-1.5 rounded-full bg-accent" />
          <span className="absolute -left-[3px] bottom-0 h-1.5 w-1.5 rounded-full bg-accent" />
        </div>

        {hero?.eyebrow && (
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-accent">
            {hero.eyebrow}
          </p>
        )}
        <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
          <h1 className="font-display text-3xl font-semibold uppercase tracking-wide text-ink md:text-4xl">
            {title}
          </h1>
          {total != null && total > 0 && (
            <span className="pb-1 text-sm font-semibold text-accent">
              {total} {pluralize(total, "товар", "товара", "товаров")}
            </span>
          )}
        </div>
        {intro && <p className="mt-3 text-sm text-ink-2 md:text-base">{intro}</p>}
        {hasCta && (
          <a
            href={hero!.ctaHref}
            className="mt-5 inline-flex items-center rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition hover:opacity-90 motion-reduce:transition-none"
          >
            {hero!.ctaLabel}
          </a>
        )}
      </div>
    </section>
  );
}
