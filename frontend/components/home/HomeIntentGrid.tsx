import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { HOME_CONTENT } from "@/lib/home-content";

// #588: сценарный вход «Что вы хотите сделать?» — карточки по задаче покупателя.
// Вместо перекрашенных lucide-иконок — предметные снимки инструмента: карточка
// про задачу, и узнаваемый инструмент считывается быстрее пиктограммы.
// Исходники 512×512 отмасштабированы в 160 px webp (1,15 МБ → 40 КБ на пять
// картинок): next.config держит images.unoptimized, файл уходит как есть.
export function HomeIntentGrid() {
  const { title, cards } = HOME_CONTENT.intent;
  return (
    <section className="bg-surface" aria-labelledby="intent-title">
      <div className="mx-auto w-full max-w-[1680px] px-4 pt-4 sm:px-6 xl:px-8">
        <h2 id="intent-title" className="mb-2 font-sans text-lg font-bold text-ink">
          {title}
        </h2>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
          {cards.map((c) => (
            <Link
              key={c.title}
              href={c.href}
              className="group flex min-h-[92px] items-center gap-3 rounded-sm border border-line bg-surface px-3 py-2 transition hover:border-accent hover:shadow-sm"
            >
              <Image
                src={c.image}
                alt=""
                width={72}
                height={72}
                className="h-[72px] w-[72px] shrink-0 object-contain transition group-hover:scale-105"
                aria-hidden
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-bold leading-tight text-ink">{c.title}</span>
                  <ArrowRight
                    className="h-3.5 w-3.5 shrink-0 text-ink-2 transition group-hover:translate-x-0.5 group-hover:text-accent"
                    aria-hidden
                  />
                </span>
                <span className="mt-1 block text-[11px] leading-[1.3] text-ink-2">{c.text}</span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
