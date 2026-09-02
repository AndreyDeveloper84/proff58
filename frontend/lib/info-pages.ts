// Информационные страницы («Доставка», «О компании», «Гарантия») — первый
// контент, который витрина берёт из админки, а не из кода.
//
// API отдаёт только опубликованное, поэтому черновик здесь просто не найдётся.
// Без INTERNAL_API_BASE_URL (сборка без бэка) возвращаем пустоту: подвал тогда
// не покажет раздел, а не упадёт.

const API_BASE = process.env.INTERNAL_API_BASE_URL;

// Как в lib/adapters.ts: nginx перед Django редиректит http→https
// (SECURE_SSL_REDIRECT). Заголовок сообщает Django через SECURE_PROXY_SSL_HEADER,
// что запрос защищён, — иначе серверный fetch ловит редирект. ТОЛЬКО server-side.
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;
// Зависший апстрим не должен вешать рендер подвала на каждой странице.
const SSR_TIMEOUT_MS = 4000;

export type InfoPageLink = { slug: string; title: string };

/** Блоки внутри секции — те же четыре, что и в статьях (разбор общий, на сервере). */
export type InfoBlock =
  | { kind: "text"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "note"; text: string };

export type InfoItem = { title: string; text: string };

/**
 * Секция страницы. `layout` задаёт вёрстку (шапка, карточки, шаги, вопросы,
 * контакты, карта), содержимое приходит из админки. Пустой layout — обычный
 * текст: так показываются страницы, написанные до появления разметки.
 */
export type InfoSection = {
  layout: "" | "hero" | "cards" | "steps" | "checklist" | "faq" | "contacts" | "map" | "chips";
  heading: string;
  meta: {
    badge?: string;
    image?: string;
    images?: string[];
    address?: string;
    phone?: string;
    email?: string;
    hours?: string;
    tone?: string;
  };
  buttons: { label: string; href: string; style: "solid" | "outline" }[];
  items: InfoItem[];
  blocks: InfoBlock[];
};

export type InfoPage = InfoPageLink & {
  body: string;
  sections: InfoSection[];
  meta_title: string;
  meta_description: string;
  updated_at: string;
};

function url(path: string): string {
  return `${API_BASE!.replace(/\/$/, "")}/api/content/${path}`;
}

/** Список страниц для меню подвала. Сбой не роняет подвал — просто нет раздела. */
export async function getInfoPageLinks(): Promise<InfoPageLink[]> {
  if (!API_BASE) return [];
  try {
    const res = await fetch(url("pages/"), {
      cache: "no-store",
      headers: SSR_HEADERS,
      signal: AbortSignal.timeout(SSR_TIMEOUT_MS),
    });
    if (!res.ok) return [];
    const json = (await res.json()) as InfoPageLink[];
    return Array.isArray(json) ? json : [];
  } catch {
    return [];
  }
}

/** Одна страница. null — нет такой или черновик (страница отдаст notFound). */
export async function getInfoPage(slug: string): Promise<InfoPage | null> {
  if (!API_BASE) return null;
  const res = await fetch(url(`pages/${encodeURIComponent(slug)}/`), {
    cache: "no-store",
    headers: SSR_HEADERS,
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Не удалось загрузить страницу «${slug}»: ${res.status}`);
  return (await res.json()) as InfoPage;
}

/** Текст из админки — обычный текст. Разбиваем на абзацы по пустой строке. */
export function toParagraphs(body: string): string[] {
  return body
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
}
