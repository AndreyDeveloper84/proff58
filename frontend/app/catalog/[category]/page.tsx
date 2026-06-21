import { Suspense } from "react";
import { notFound } from "next/navigation";
import { getListing } from "@/lib/catalog";
import { ListingShell } from "@/components/listing/ListingShell";

type Params = { params: Promise<{ category: string }> };

export async function generateMetadata({ params }: Params) {
  const { category } = await params;
  const listing = await getListing(category);
  if (!listing) return { title: "Категория не найдена — Профессионал" };
  return {
    title: `${listing.category.title} — Профессионал`,
    description: listing.category.intro,
  };
}

export default async function CategoryPage({ params }: Params) {
  const { category } = await params;
  const listing = await getListing(category);
  if (!listing) notFound();

  return (
    <Suspense fallback={<div className="p-10 text-sm text-ink-3">Загрузка каталога…</div>}>
      <ListingShell listing={listing} categorySlug={category} />
    </Suspense>
  );
}
