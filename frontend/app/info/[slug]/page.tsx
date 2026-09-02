import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { InfoSection } from "@/components/info/InfoSection";
import { getInfoPage, toParagraphs } from "@/lib/info-pages";

type Props = { params: Promise<{ slug: string }> };

// Страницы редактируются в админке — пререндер зацементировал бы их до
// следующей сборки. revalidate в fetch (5 минут) даёт кэш без этого.
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const page = await getInfoPage(slug);
  if (!page) return {};
  return {
    title: page.meta_title || page.title,
    description: page.meta_description || undefined,
    alternates: { canonical: `/info/${slug}` },
  };
}

export default async function InfoPageView({ params }: Props) {
  const { slug } = await params;
  const page = await getInfoPage(slug);
  if (!page) notFound();

  const sections = page.sections ?? [];
  // Страница, написанная до появления разметки, состоит из одних абзацев —
  // показываем её как раньше, а не пустым местом.
  const paragraphs = sections.length === 0 ? toParagraphs(page.body) : [];
  // Заголовок страницы рисует шапка. Если её нет (старый контент) — ставим h1 сами:
  // страница без единственного h1 ломает и разметку, и скринридер.
  const hasHero = sections.some((section) => section.layout === "hero");

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <nav aria-label="Хлебные крошки" className="text-sm text-ink-3">
        <Link href="/" className="text-accent hover:underline">
          Главная
        </Link>
        <span className="px-2">/</span>
        <span className="text-ink-2">{page.title}</span>
      </nav>

      {hasHero ? null : (
        <h1 className="mt-6 font-display text-2xl font-bold tracking-tight text-ink sm:text-3xl">
          {page.title}
        </h1>
      )}

      {sections.length > 0 ? (
        <div className="mt-8 space-y-12 sm:space-y-16">
          {sections.map((section, index) => (
            <InfoSection key={`${section.layout}-${section.heading}-${index}`} section={section} />
          ))}
        </div>
      ) : paragraphs.length > 0 ? (
        <div className="mt-6 max-w-3xl space-y-4 text-base leading-relaxed text-ink-2">
          {/* Текст выводим как текст, а не как HTML: страницу пишет человек в
              админке, и вставка разметки открыла бы XSS через редактора. */}
          {paragraphs.map((text, index) => (
            <p key={index} className="whitespace-pre-line">
              {text}
            </p>
          ))}
        </div>
      ) : (
        <p className="mt-6 text-ink-2">Страница пока не заполнена.</p>
      )}
    </main>
  );
}
