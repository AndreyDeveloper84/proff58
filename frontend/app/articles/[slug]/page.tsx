import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, CalendarDays, Clock, Info, MessageSquareText } from "lucide-react";
import { BatteryStorageFigure } from "@/components/articles/figures/BatteryStorageFigure";
import { BurWearFigure } from "@/components/articles/figures/BurWearFigure";
import { DiscMarkingFigure } from "@/components/articles/figures/DiscMarkingFigure";
import { DutyCycleFigure } from "@/components/articles/figures/DutyCycleFigure";
import { SdsShankFigure } from "@/components/articles/figures/SdsShankFigure";
import { TorqueScaleFigure } from "@/components/articles/figures/TorqueScaleFigure";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { ProductCard } from "@/components/product/ProductCard";
import { type ArticleBlock, type ArticleFigure } from "@/lib/articles";
import { getArticleBySlug, getArticleCards } from "@/lib/articles-source";
import { getCategoryProducts } from "@/lib/catalog";
import { SITE } from "@/lib/site";

type Props = { params: Promise<{ slug: string }> };

// Блок «подобрать по теме» показывает живые цены и наличие, поэтому страница
// рендерится на запрос: пререндер зацементировал бы витрину на момент сборки.
export const dynamic = "force-dynamic";

// Схема открывает статью вместо фото: предметный снимок категории на всю ширину
// ничего не объясняет, а чертёж отвечает ровно на вопрос, с которым пришли.
const FIGURES: Record<ArticleFigure, React.ComponentType> = {
  "sds-shank": SdsShankFigure,
  "battery-storage": BatteryStorageFigure,
  "torque-scale": TorqueScaleFigure,
  "disc-marking": DiscMarkingFigure,
  "duty-cycle": DutyCycleFigure,
  "bur-wear": BurWearFigure,
};

export async function generateMetadata({ params }: Props) {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) return { title: "Статья не найдена" };
  return { title: article.title, description: article.excerpt };
}

function Block({ block }: { block: ArticleBlock }) {
  if (block.kind === "text") {
    return <p className="mt-3 text-[13px] leading-[1.65] text-ink-2">{block.text}</p>;
  }

  if (block.kind === "list") {
    return (
      <ul className="mt-3 space-y-2">
        {block.items.map((item) => (
          <li key={item} className="flex gap-2 text-[13px] leading-[1.6] text-ink-2">
            <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
            <span className="min-w-0">{item}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (block.kind === "table") {
    return (
      <div className="mt-3 overflow-x-auto rounded-sm border border-line">
        <table className="w-full min-w-[420px] border-collapse text-[12px]">
          <thead>
            <tr className="bg-raised">
              {block.head.map((cell) => (
                <th key={cell} className="px-3 py-2 text-left font-semibold text-ink">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row) => (
              <tr key={row.join("|")} className="border-t border-line">
                {row.map((cell, index) => (
                  <td
                    key={cell}
                    className={index === 0 ? "px-3 py-2 font-medium text-ink" : "px-3 py-2 text-ink-2"}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <p className="mt-3 flex gap-2 rounded-sm border border-line bg-raised px-3 py-2.5 text-[12px] leading-[1.55] text-ink-2">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
      <span>{block.text}</span>
    </p>
  );
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) notFound();

  const more = (await getArticleCards())
    .filter((item) => item.slug !== article.slug)
    .slice(0, 3);
  const Figure = FIGURES[article.figure];
  const products = article.catalog ? await getCategoryProducts(article.catalog.slug, 3) : [];

  return (
    <main className="min-h-[70vh] bg-surface pb-20 lg:pb-0">
      <div className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6 lg:px-4">
        <nav aria-label="Хлебные крошки" className="mb-3 flex flex-wrap items-center gap-2 text-xs text-ink-3">
          <Link href="/" className="transition hover:text-accent">
            Главная
          </Link>
          <span aria-hidden>›</span>
          <Link href="/articles" className="transition hover:text-accent">
            Статьи
          </Link>
          <span aria-hidden>›</span>
          <span className="line-clamp-1 text-ink-2">{article.title}</span>
        </nav>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_300px]">
          <article className="min-w-0">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-accent">
              {article.tag}
            </span>
            <h1 className="mt-1 font-display text-[26px] font-semibold leading-tight text-ink lg:text-[32px]">
              {article.title}
            </h1>
            <p className="mt-2 flex items-center gap-3 text-[11px] text-ink-3">
              <span className="inline-flex items-center gap-1">
                <CalendarDays className="h-3.5 w-3.5" aria-hidden />
                <time dateTime={article.date}>{article.dateLabel}</time>
              </span>
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" aria-hidden />
                {article.readingMinutes} мин чтения
              </span>
            </p>

            <div className="mt-3">
              <Figure />
            </div>

            <p className="mt-3 text-[14px] leading-[1.6] text-ink">{article.excerpt}</p>

            <section
              aria-label="Коротко"
              className="mt-3 rounded-md border border-line bg-raised px-4 py-3"
            >
              <h2 className="text-[11px] font-bold uppercase tracking-wide text-ink-3">Коротко</h2>
              <ul className="mt-2 space-y-1.5">
                {article.summary.map((item) => (
                  <li key={item} className="flex gap-2 text-[12px] leading-[1.5] text-ink">
                    <span className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                    <span className="min-w-0">{item}</span>
                  </li>
                ))}
              </ul>
            </section>

            {article.sections.map((section) => (
              <section key={section.heading} className="mt-6">
                <h2 className="font-sans text-[17px] font-bold leading-tight text-ink">
                  {section.heading}
                </h2>
                {section.blocks.map((block, index) => (
                  <Block key={`${section.heading}-${index}`} block={block} />
                ))}
              </section>
            ))}

            {/* Витрина по теме статьи: цены и наличие живые, из каталога. Пусто
                (нет API или раздел не заполнен) — блок просто не рисуется. */}
            {article.catalog && products.length > 0 && (
              <section className="mt-6" aria-label="Товары по теме статьи">
                <div className="mb-2 flex flex-wrap items-baseline gap-2">
                  <h2 className="font-sans text-[17px] font-bold text-ink">Подобрать по теме</h2>
                  <Link
                    href={`/catalog/${article.catalog.slug}`}
                    className="ml-auto inline-flex items-center gap-1 text-[12px] font-semibold text-accent transition hover:gap-1.5"
                  >
                    {article.catalog.label}
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {products.map((product) => (
                    <ProductCard key={product.id} product={product} view="grid" />
                  ))}
                </div>
              </section>
            )}

            {article.catalog && products.length === 0 && (
              <Link
                href={`/catalog/${article.catalog.slug}`}
                className="mt-6 flex items-center gap-3 rounded-md border border-line bg-surface px-4 py-3 transition hover:border-accent/60 hover:shadow-sm"
              >
                <span className="min-w-0 flex-1">
                  <span className="block text-[11px] text-ink-3">Подобрать в каталоге</span>
                  <span className="block text-sm font-semibold text-ink">
                    {article.catalog.label}
                  </span>
                </span>
                <ArrowRight className="h-4 w-4 shrink-0 text-accent" aria-hidden />
              </Link>
            )}
          </article>

          <aside className="min-w-0 space-y-2.5 lg:sticky lg:top-4 lg:self-start">
            <div className="rounded-md border border-line bg-[linear-gradient(135deg,var(--surface)_0%,var(--max-tint)_100%)] p-3.5">
              <div className="relative pr-12">
                <Image
                  src="/brands/max-colored.png"
                  alt=""
                  width={48}
                  height={48}
                  className="absolute right-0 top-0 h-10 w-10 object-contain"
                  aria-hidden
                />
                <h2 className="font-sans text-sm font-bold leading-tight text-ink">
                  Остались вопросы по выбору?
                </h2>
                <p className="mt-1 text-[11px] leading-[1.35] text-ink-2">
                  Опишите задачу в MAX — подберём модель под материал, объём и бюджет.
                </p>
              </div>
              <a
                href={SITE.support.max.href}
                target="_blank"
                rel="noopener noreferrer"
                data-event="article_max_click"
                className="mt-2.5 inline-flex h-9 items-center justify-center gap-1.5 rounded-sm bg-[#6156f5] px-3 text-xs font-semibold text-white transition hover:bg-[#5147dc]"
              >
                <MessageSquareText className="h-4 w-4" aria-hidden />
                Консультация в MAX
              </a>
            </div>

            <div className="rounded-md border border-line bg-surface p-3.5">
              <h2 className="font-sans text-sm font-bold text-ink">Читайте также</h2>
              <ul className="mt-2 space-y-2">
                {more.map((item) => (
                  <li key={item.slug}>
                    <Link href={`/articles/${item.slug}`} className="group flex gap-2">
                      <span className="relative h-11 w-14 shrink-0 overflow-hidden rounded-sm bg-photo">
                        <Image
                          src={item.image}
                          alt=""
                          fill
                          sizes="56px"
                          className="object-cover"
                          style={{ objectPosition: item.imagePosition ?? "50% 50%" }}
                          aria-hidden
                        />
                      </span>
                      <span className="min-w-0">
                        <span className="line-clamp-2 block text-[11px] font-semibold leading-[1.3] text-ink transition group-hover:text-accent">
                          {item.title}
                        </span>
                        <span className="mt-0.5 block text-[10px] text-ink-3">{item.dateLabel}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              <Link
                href="/articles"
                className="mt-2.5 inline-flex items-center gap-1 text-[11px] font-semibold text-accent transition hover:gap-1.5"
              >
                Все статьи
                <ArrowRight className="h-3 w-3" aria-hidden />
              </Link>
            </div>
          </aside>
        </div>
      </div>

      <MobileBottomNav active="catalog" />
    </main>
  );
}
