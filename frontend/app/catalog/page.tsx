import { redirect } from "next/navigation";

// Категорию для редиректа выбираем в рантайме (из API), а не «запекаем» при сборке.
export const dynamic = "force-dynamic";

// Индекс каталога: ведём на ПЕРВУЮ реальную категорию из API (slug из БД, не хардкод).
// Локально/без API — на демо-категорию фикстуры. Если API недоступен — страница-заглушка
// (не постоянный redirect на тестовый slug).
async function firstCategorySlug(): Promise<string | null> {
  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base) return "perforatory";
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}/api/catalog/categories/`, {
      cache: "no-store",
      headers: { "X-Forwarded-Proto": "https" },
    });
    if (!res.ok) return null;
    const tree = (await res.json()) as { slug?: string }[];
    return Array.isArray(tree) && tree[0]?.slug ? tree[0].slug : null;
  } catch {
    return null;
  }
}

export default async function CatalogIndexPage() {
  const slug = await firstCategorySlug();
  if (slug) redirect(`/catalog/${slug}`);
  return (
    <div className="mx-auto max-w-md px-4 py-20 text-center">
      <h1 className="font-display text-2xl font-semibold text-ink">Каталог временно недоступен</h1>
      <p className="mt-2 text-sm text-ink-2">Обновите страницу позже.</p>
    </div>
  );
}
