import Image from "next/image";
import Link from "next/link";
import { ArrowRight, CalendarDays, Clock } from "lucide-react";
import { WhyBuyStrip } from "@/components/home/HomeBottom";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { ARTICLES } from "@/lib/articles";

export const metadata = { title: "Статьи и обзоры" };

export default function ArticlesIndexPage() {
  const [lead, ...rest] = ARTICLES;

  return (
    <main className="min-h-[70vh] bg-surface pb-20 lg:pb-0">
      <div className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6 lg:px-4">
        <nav aria-label="Хлебные крошки" className="mb-3 flex items-center gap-2 text-xs text-ink-3">
          <Link href="/" className="transition hover:text-accent">
            Главная
          </Link>
          <span aria-hidden>›</span>
          <span className="text-ink-2">Статьи</span>
        </nav>

        <h1 className="font-display text-[28px] font-semibold text-ink lg:text-[32px]">
          Статьи и обзоры
        </h1>
        <p className="mt-1 max-w-[640px] text-sm text-ink-2">
          Разбираем характеристики инструмента и оснастки так, чтобы по ним можно было выбирать:
          что означают цифры в паспорте и на что они влияют в работе.
        </p>

        {/* Первая статья — крупной карточкой, остальные сеткой: список короткий,
            и однородная плитка выглядела бы пустовато. */}
        <section aria-label="Все статьи" className="mt-5 grid gap-2.5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Link
            href={`/articles/${lead.slug}`}
            className="group flex flex-col overflow-hidden rounded-md border border-line bg-surface transition hover:border-accent/60 hover:shadow-md lg:self-start"
          >
            {/* Предметное фото — contain на светлом фоне: кадрирование крупной
                обложки оставило бы от инструмента непонятный фрагмент. */}
            <span className="relative block h-[200px] w-full bg-photo sm:h-[240px]">
              <Image
                src={lead.image}
                alt=""
                fill
                priority
                sizes="(max-width: 1023px) 100vw, 700px"
                className="object-contain p-4 transition duration-300 group-hover:scale-[1.02]"
                aria-hidden
              />
            </span>
            <span className="flex flex-1 flex-col p-4">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-accent">
                {lead.tag}
              </span>
              <span className="mt-1 block font-display text-[20px] font-semibold leading-tight text-ink transition group-hover:text-accent">
                {lead.title}
              </span>
              <span className="mt-1.5 line-clamp-3 block text-sm leading-[1.45] text-ink-2">
                {lead.excerpt}
              </span>
              <span className="mt-auto flex items-center gap-3 pt-3 text-[11px] text-ink-3">
                <span className="inline-flex items-center gap-1">
                  <CalendarDays className="h-3.5 w-3.5" aria-hidden />
                  {lead.dateLabel}
                </span>
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" aria-hidden />
                  {lead.readingMinutes} мин чтения
                </span>
                <span className="ml-auto inline-flex items-center gap-1 font-semibold text-accent">
                  Читать
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
                </span>
              </span>
            </span>
          </Link>

          <ul className="grid gap-2.5 sm:grid-cols-2 lg:content-start">
            {rest.map((article) => (
              <li key={article.slug}>
                <Link
                  href={`/articles/${article.slug}`}
                  className="group flex h-full flex-col overflow-hidden rounded-md border border-line bg-surface transition hover:border-accent/60 hover:shadow-sm"
                >
                  <span className="relative block h-[104px] w-full bg-photo">
                    <Image
                      src={article.image}
                      alt=""
                      fill
                      sizes="(max-width: 639px) 100vw, 340px"
                      className="object-contain p-2 transition duration-300 group-hover:scale-[1.03]"
                      aria-hidden
                    />
                  </span>
                  <span className="flex flex-1 flex-col p-3">
                    <span className="text-[9px] font-semibold uppercase tracking-wide text-accent">
                      {article.tag}
                    </span>
                    <span className="mt-0.5 line-clamp-2 block text-[13px] font-semibold leading-[1.3] text-ink transition group-hover:text-accent">
                      {article.title}
                    </span>
                    <span className="mt-1 line-clamp-2 block text-[11px] leading-[1.4] text-ink-2">
                      {article.excerpt}
                    </span>
                    <span className="mt-auto flex items-center gap-2 pt-2 text-[10px] text-ink-3">
                      <span className="inline-flex items-center gap-1">
                        <CalendarDays className="h-3 w-3" aria-hidden />
                        {article.dateLabel}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3 w-3" aria-hidden />
                        {article.readingMinutes} мин
                      </span>
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-3">
          <WhyBuyStrip />
        </div>
      </div>

      <MobileBottomNav active="catalog" />
    </main>
  );
}
