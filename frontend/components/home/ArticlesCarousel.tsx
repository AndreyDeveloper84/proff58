"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, CalendarDays, ChevronLeft, ChevronRight, Clock } from "lucide-react";
import type { Article } from "@/lib/articles";
import { cn } from "@/lib/utils";

// Лента советов (материалы раздела /articles): горизонтальный scroll-snap вместо
// JS-анимации — так листание работает и без гидратации, и жестом на телефоне.
// На xl в кадре три карточки, на планшете две — стрелки листают по одной; на
// мобильной карточка занимает 82 % ширины (край следующей виден — подсказка,
// что лента прокручивается), стрелки скрыты, а положение показывает ряд точек.
// Когда материалов не больше трёх, на xl видны все — стрелки там не нужны.
export function ArticlesCarousel({ articles }: { articles: Article[] }) {
  const headingId = useId();
  const fitsOnDesktop = articles.length <= 3;
  const trackRef = useRef<HTMLUListElement>(null);
  const [active, setActive] = useState(0);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);

  const sync = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const card = track.firstElementChild as HTMLElement | null;
    const step = card ? card.getBoundingClientRect().width + 10 : 1;
    setActive(Math.round(track.scrollLeft / step));
    setAtStart(track.scrollLeft < 8);
    setAtEnd(track.scrollLeft + track.clientWidth >= track.scrollWidth - 8);
  }, []);

  useEffect(() => {
    sync();
    const track = trackRef.current;
    if (!track) return;
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, [sync]);

  const scrollBy = (direction: -1 | 1) => {
    const track = trackRef.current;
    if (!track) return;
    const card = track.firstElementChild as HTMLElement | null;
    const step = card ? card.getBoundingClientRect().width + 10 : track.clientWidth;
    track.scrollBy({ left: step * direction, behavior: "smooth" });
  };

  const scrollTo = (index: number) => {
    const track = trackRef.current;
    if (!track) return;
    const card = track.firstElementChild as HTMLElement | null;
    const step = card ? card.getBoundingClientRect().width + 10 : track.clientWidth;
    track.scrollTo({ left: step * index, behavior: "smooth" });
  };

  return (
    <section className="min-w-0" aria-labelledby={headingId}>
      <div className="mb-2 flex items-center gap-2">
        {/* На телефоне полное название не помещается в строку со ссылкой —
            там короткое «Полезные советы». Скрытый вариант (display: none)
            не попадает в имя заголовка, озвучивается только видимый. */}
        <h2 id={headingId} className="min-w-0 font-sans text-sm font-bold text-ink">
          <span className="sm:hidden">Полезные советы</span>
          <span className="hidden sm:inline">Советы по выбору и работе с инструментом</span>
        </h2>
        <Link
          href="/articles"
          className="ml-auto inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-sm font-semibold text-accent transition hover:gap-1.5"
        >
          Все советы
          <ArrowRight className="h-3 w-3" aria-hidden />
        </Link>
        <div
          data-testid="articles-arrows"
          className={cn("hidden gap-1 sm:flex", fitsOnDesktop && "xl:hidden")}
        >
          <button
            type="button"
            onClick={() => scrollBy(-1)}
            disabled={atStart}
            aria-label="Предыдущие советы"
            className="grid h-11 w-11 place-items-center rounded-sm border border-line bg-surface sm:h-9 sm:w-9 text-ink-2 transition hover:border-accent hover:text-accent disabled:opacity-40 disabled:hover:border-line disabled:hover:text-ink-2"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => scrollBy(1)}
            disabled={atEnd}
            aria-label="Следующие советы"
            className="grid h-11 w-11 place-items-center rounded-sm border border-line bg-surface sm:h-9 sm:w-9 text-ink-2 transition hover:border-accent hover:text-accent disabled:opacity-40 disabled:hover:border-line disabled:hover:text-ink-2"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>

      <ul
        ref={trackRef}
        onScroll={sync}
        className="flex snap-x snap-mandatory gap-2.5 overflow-x-auto scroll-smooth pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {articles.map((article) => (
          <li
            key={article.slug}
            className="w-[82%] shrink-0 snap-start sm:w-[calc((100%-10px)/2)] xl:w-[calc((100%-20px)/3)]"
          >
            <Link
              href={`/articles/${article.slug}`}
              className="group flex h-full min-h-[124px] items-stretch overflow-hidden rounded-sm border border-line bg-card shadow-card transition hover:border-accent/60 hover:shadow-md"
            >
              <span className="relative w-[104px] shrink-0 bg-photo">
                <Image
                  src={article.image}
                  alt=""
                  fill
                  sizes="86px"
                  className="object-cover transition duration-300 group-hover:scale-[1.04]"
                  style={{ objectPosition: article.imagePosition ?? "50% 50%" }}
                  aria-hidden
                />
              </span>
              <span className="flex min-w-0 flex-col p-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-accent">
                  {article.tag}
                </span>
                <span className="mt-0.5 line-clamp-2 block text-sm font-semibold leading-[1.3] text-ink transition group-hover:text-accent">
                  {article.title}
                </span>
                {/* nowrap: в узкой карточке дата иначе ломается на «20 июля» / «2026». */}
                <span className="mt-auto flex flex-wrap items-center gap-x-2 pt-1 text-xs text-ink-3">
                  <span className="inline-flex items-center gap-1 whitespace-nowrap">
                    <CalendarDays className="h-3 w-3 shrink-0" aria-hidden />
                    {article.dateLabel}
                  </span>
                  <span className="inline-flex items-center gap-1 whitespace-nowrap">
                    <Clock className="h-3 w-3 shrink-0" aria-hidden />
                    {article.readingMinutes} мин
                  </span>
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {/* Точки — навигация мобильной версии: показывают, сколько ещё советов
          в ленте, и переключают карточку тапом. */}
      <div className="mt-1.5 flex justify-center gap-1.5 sm:hidden">
        {articles.map((article, index) => (
          <button
            key={article.slug}
            type="button"
            onClick={() => scrollTo(index)}
            aria-label={`Совет ${index + 1}: ${article.title}`}
            aria-current={index === active}
            className={cn(
              "h-1.5 rounded-full transition-all",
              index === active ? "w-4 bg-accent" : "w-1.5 bg-line",
            )}
          />
        ))}
      </div>
    </section>
  );
}
