import type { Metadata } from "next";
import { notFound } from "next/navigation";
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
  };
}

export default async function InfoPageView({ params }: Props) {
  const { slug } = await params;
  const page = await getInfoPage(slug);
  if (!page) notFound();

  const paragraphs = toParagraphs(page.body);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{page.title}</h1>

      {paragraphs.length > 0 ? (
        <div className="mt-6 space-y-4 text-base leading-relaxed text-muted-foreground">
          {/* Текст выводим как текст, а не как HTML: страницу пишет человек в
              админке, и вставка разметки открыла бы XSS через редактора. */}
          {paragraphs.map((text, index) => (
            <p key={index} className="whitespace-pre-line">
              {text}
            </p>
          ))}
        </div>
      ) : (
        <p className="mt-6 text-muted-foreground">Страница пока не заполнена.</p>
      )}
    </main>
  );
}
