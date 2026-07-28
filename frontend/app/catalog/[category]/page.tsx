import { Suspense } from "react";
import { notFound } from "next/navigation";
import { getCategoryLookup, getListing } from "@/lib/catalog";
import { parseQuery } from "@/lib/url-state";
import { CatalogSkeleton } from "@/components/listing/CatalogSkeleton";
import { ListingShell } from "@/components/listing/ListingShell";

type Props = {
  params: Promise<{ category: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

// Заголовок — витринное название раздела из API; slug остаётся запасным вариантом
// на случай недоступного API. Суффикс «— Профессионал» дописывает шаблон title
// из app/layout.tsx — здесь его повторять не нужно.
export async function generateMetadata({ params }: Props) {
  const { category } = await params;
  const lookup = await getCategoryLookup(category);
  return {
    title:
      lookup.status === "found" ? lookup.name : `Каталог: ${category.replace(/[-_]/g, " ")}`,
  };
}

function toSearchParams(
  sp: Record<string, string | string[] | undefined>,
): URLSearchParams {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(sp)) {
    if (Array.isArray(v)) v.forEach((x) => usp.append(k, x));
    else if (v != null) usp.set(k, v);
  }
  return usp;
}

// Товары и фасеты (два запроса к каталогу) стримятся под скелетоном — но уже
// после того, как страница убедилась, что раздел существует.
async function CategoryListing({
  category,
  searchParams,
}: {
  category: string;
  searchParams: Props["searchParams"];
}) {
  const sp = await searchParams;
  const query = parseQuery(toSearchParams(sp), category);
  const listing = await getListing(query);
  if (!listing) notFound();

  return <ListingShell listing={listing} query={query} />;
}

export default async function CategoryPage({ params, searchParams }: Props) {
  const { category } = await params;

  // Существование раздела проверяем ДО Suspense-границы: как только отрендерится
  // её фоллбэк, ответ уходит клиенту и HTTP-статус уже не изменить — notFound()
  // из стримящейся части отдал бы 404-страницу с кодом 200 (Next 16,
  // «loading#status-codes»). Поэтому скелетон живёт здесь, а не в loading.tsx.
  // Недоступный API — не повод для 404: страница идёт дальше и покажет ошибку.
  const lookup = await getCategoryLookup(category);
  if (lookup.status === "missing") notFound();

  return (
    <Suspense fallback={<CatalogSkeleton />}>
      <CategoryListing category={category} searchParams={searchParams} />
    </Suspense>
  );
}
