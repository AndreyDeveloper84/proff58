// Источник статей: сначала админка, потом встроенные.
//
// Статьи переезжают в БД постепенно. Если просто переключить витрину на API,
// пустая база означала бы сайт без шести готовых статей — регресс на ровном
// месте. Поэтому правило: есть в админке — берём оттуда, нет — показываем
// встроенную. Слитые в БД статьи перекрывают одноимённые встроенные по slug.
//
// Когда весь контент переедет, останется удалить fallback и сам ARTICLES.

import { ARTICLES, type Article } from "./articles";

const API_BASE = process.env.INTERNAL_API_BASE_URL;

// Как в lib/adapters.ts: без этого заголовка nginx перед Django редиректит
// http→https и серверный запрос ломается. ТОЛЬКО server-side.
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;
const SSR_TIMEOUT_MS = 4000;

/** Карточка ленты: то, что нужно списку и каруселям на главной. */
export type ArticleCard = Pick<
  Article,
  "slug" | "title" | "excerpt" | "tag" | "figure" | "image" | "date" | "readingMinutes"
> & {
  dateLabel: string;
  /** Кадрирование обложки. Есть только у встроенных статей: у загруженных из
      админки обложка своя, и подгонять её положение вручную некому. */
  imagePosition?: string;
};

const MONTHS = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

/** «2026-07-20» → «20 июля 2026». Пустая дата — пустая подпись. */
export function formatDateLabel(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? "");
  if (!match) return "";
  const [, year, month, day] = match;
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

function toCard(article: Article): ArticleCard {
  return {
    slug: article.slug,
    title: article.title,
    excerpt: article.excerpt,
    tag: article.tag,
    figure: article.figure,
    image: article.image,
    date: article.date,
    dateLabel: article.dateLabel,
    readingMinutes: article.readingMinutes,
    imagePosition: article.imagePosition,
  };
}

async function fromApi<T>(path: string, soft: boolean): Promise<T | null> {
  if (!API_BASE) return null;
  const url = `${API_BASE.replace(/\/$/, "")}/api/content/${path}`;
  try {
    const res = await fetch(url, {
      cache: "no-store",
      headers: SSR_HEADERS,
      signal: AbortSignal.timeout(SSR_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    if (!soft) throw new Error(`Не удалось загрузить ${path}`);
    return null;
  }
}

type ApiCard = Omit<ArticleCard, "dateLabel">;

/** Лента статей: из админки плюс встроенные, которых там ещё нет. */
export async function getArticleCards(): Promise<ArticleCard[]> {
  const fromDb = (await fromApi<ApiCard[]>("articles/", true)) ?? [];
  const cards = fromDb.map((card) => ({ ...card, dateLabel: formatDateLabel(card.date) }));

  const seen = new Set(cards.map((card) => card.slug));
  const builtin = ARTICLES.filter((article) => !seen.has(article.slug)).map(toCard);
  return [...cards, ...builtin].sort((a, b) => (a.date < b.date ? 1 : -1));
}

/** Одна статья: приоритет у админки, дальше встроенная, иначе null → 404. */
export async function getArticleBySlug(slug: string): Promise<Article | null> {
  const fromDb = await fromApi<Omit<Article, "dateLabel"> | null>(
    `articles/${encodeURIComponent(slug)}/`,
    true,
  );
  if (fromDb) {
    return { ...fromDb, dateLabel: formatDateLabel(fromDb.date) } as Article;
  }
  return ARTICLES.find((article) => article.slug === slug) ?? null;
}
