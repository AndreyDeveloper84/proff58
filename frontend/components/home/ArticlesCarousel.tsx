"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, CalendarDays, ChevronLeft, ChevronRight, Clock } from "lucide-react";
import type { Article } from "@/lib/articles";
import { cn } from "@/lib/utils";

// Лента статей: горизонтальный scroll-snap вместо JS-анимации — так листание
// работает и без гидратации, и жестом на телефоне. На десктопе в кадре три
// карточки и стрелки листают по одной; на мобильной карточка занимает 82 %
// ширины (край следующей виден — подсказка, что лента прокручивается),
// стрелки скрыты, а положение показывает ряд точек.
export function ArticlesCarousel({ articles }: { articles: Article[] }) {
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
    <div className="min-w-0" aria-label="Полезные статьи и обзоры">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="font-sans text-sm font-bold text-ink">Полезные статьи и обзоры</h2>
        <Link
          href="/articles"
          className="ml-auto inline-flex items-center gap-1 text-[11px] font-semibold text-accent transition hover:gap-1.5"
        >
          Все статьи
          <ArrowRight className="h-3 w-3" aria-hidden />
        </Link>
        <div className="hidden gap-1 sm:flex">
          <button
            type="button"
            onClick={() => scrollBy(-1)}
            disabled={atStart}
            aria-label="Предыдущие статьи"
            className="grid h-11 w-11 place-items-center rounded-sm border border-line bg-surface sm:h-6 sm:w-6 text-ink-2 transition hover:border-accent hover:text-accent disabled:opacity-40 disabled:hover:border-line disabled:hover:text-ink-2"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => scrollBy(1)}
            disabled={atEnd}
            aria-label="Следующие статьи"
            className="grid h-11 w-11 place-items-center rounded-sm border border-line bg-surface sm:h-6 sm:w-6 text-ink-2 transition hover:border-accent hover:text-accent disabled:opacity-40 disabled:hover:border-line disabled:hover:text-ink-2"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>

      <ul
        ref={trackRef}
        onScroll={sync}
        className="-mx-1 flex snap-x snap-mandatory gap-2.5 overflow-x-auto scroll-smooth px-1 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {articles.map((article) => (
          <li
            key={article.slug}
            className="w-[82%] shrink-0 snap-start sm:w-[calc((100%-10px)/2)] xl:w-[calc((100%-20px)/3)]"
          >
            <Link
              href={`/articles/${article.slug}`}
              className="group flex h-full min-h-[92px] items-stretch overflow-hidden rounded-sm border border-line bg-surface transition hover:border-accent/60 hover:shadow-sm"
            >
              <span className="relative w-[86px] shrink-0 bg-photo">
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
                <span className="text-[9px] font-semibold uppercase tracking-wide text-accent">
                  {article.tag}
                </span>
                <span className="mt-0.5 line-clamp-2 block text-[11px] font-semibold leading-[1.3] text-ink transition group-hover:text-accent">
                  {article.title}
                </span>
                {/* nowrap: в узкой карточке дата иначе ломается на «20 июля» / «2026». */}
                <span className="mt-auto flex flex-wrap items-center gap-x-2 pt-1 text-[10px] text-ink-3">
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

      {/* Точки — навигация мобильной версии: показывают, сколько ещё статей
          в ленте, и переключают карточку тапом. */}
      <div className="mt-1.5 flex justify-center gap-1.5 sm:hidden">
        {articles.map((article, index) => (
          <button
            key={article.slug}
            type="button"
            onClick={() => scrollTo(index)}
            aria-label={`Статья ${index + 1}: ${article.title}`}
            aria-current={index === active}
            className={cn(
              "h-1.5 rounded-full transition-all",
              index === active ? "w-4 bg-accent" : "w-1.5 bg-line",
            )}
          />
        ))}
      </div>
    </div>
  );
}
