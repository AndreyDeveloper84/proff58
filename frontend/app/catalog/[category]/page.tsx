import { notFound } from "next/navigation";
import { getListing } from "@/lib/catalog";
import { parseQuery } from "@/lib/url-state";
import { ListingShell } from "@/components/listing/ListingShell";

type Props = {
  params: Promise<{ category: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export async function generateMetadata({ params }: Props) {
  const { category } = await params;
  const title = category.replace(/[-_]/g, " ");
  return { title: `Каталог: ${title} — Профессионал` };
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

export default async function CategoryPage({ params, searchParams }: Props) {
  const { category } = await params;
  const sp = await searchParams;
  const query = parseQuery(toSearchParams(sp), category);
  const listing = await getListing(query);
  if (!listing) notFound();

  return <ListingShell listing={listing} query={query} />;
}
