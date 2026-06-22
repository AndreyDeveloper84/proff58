import Link from "next/link";

// Категории берём из API в рантайме (slug'и из БД), без редиректа.
export const dynamic = "force-dynamic";

type CategoryNode = { id: number; name: string; slug: string; children?: CategoryNode[] };

async function getCategories(): Promise<CategoryNode[] | null> {
  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base) {
    // Локально/без API — демо-категория фикстуры.
    return [{ id: 0, name: "Перфораторы (демо)", slug: "perforatory" }];
  }
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}/api/catalog/categories/`, {
      cache: "no-store",
      headers: { "X-Forwarded-Proto": "https" }, // server-side: обход SSL-redirect Django
    });
    if (!res.ok) return null;
    const tree = (await res.json()) as CategoryNode[];
    return Array.isArray(tree) ? tree : null;
  } catch {
    return null;
  }
}

export async function generateMetadata() {
  return { title: "Каталог — Профессионал" };
}

export default async function CatalogIndexPage() {
  const categories = await getCategories();

  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6">
      <nav
        aria-label="Хлебные крошки"
        className="mb-3 flex flex-wrap items-center gap-1 text-xs text-ink-3"
      >
        <Link href="/" className="hover:text-accent">
          Главная
        </Link>
        <span className="text-ink-3">/</span>
        <span className="text-ink-2">Каталог</span>
      </nav>

      <h1 className="mb-6 font-display text-3xl font-semibold uppercase tracking-wide text-ink">
        Каталог
      </h1>

      {categories == null ? (
        <div className="rounded-lg border border-line bg-surface p-10 text-center text-ink-2">
          Каталог временно недоступен. Обновите страницу позже.
        </div>
      ) : categories.length === 0 ? (
        <div className="rounded-lg border border-line bg-surface p-10 text-center text-ink-2">
          Категории пока не заполнены.
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {categories.map((c) => (
            <li key={c.id}>
              <Link
                href={`/catalog/${c.slug}`}
                className="group flex h-full flex-col gap-1 rounded-lg border border-line bg-raised p-4 transition hover:border-accent/60"
              >
                <span className="font-display text-lg font-semibold text-ink group-hover:text-accent">
                  {c.name}
                </span>
                {c.children && c.children.length > 0 && (
                  <span className="text-xs text-ink-3">подкатегорий: {c.children.length}</span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
