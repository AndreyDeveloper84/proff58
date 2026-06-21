// Слой данных каталога. Сейчас читает фикстуру; на SP3 здесь будет fetch к DRF
// (/api/catalog/...), а вызывающий код (page.tsx/ListingShell) не меняется.

import perforatory from "@/fixtures/listing.perforatory.json";
import type { Listing } from "./types";

const FIXTURES: Record<string, Listing> = {
  perforatory: perforatory as unknown as Listing,
};

export async function getListing(category: string): Promise<Listing | null> {
  return FIXTURES[category] ?? null;
}

export function listingCategories(): string[] {
  return Object.keys(FIXTURES);
}
