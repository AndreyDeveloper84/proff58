import type { ProductDetail } from "@/lib/types";

// Серверная микроразметка для поисковиков: Product + Offer + BreadcrumbList.
// Рендерит один <script type="application/ld+json"> с массивом из двух объектов.
export function ProductJsonLd({
  product,
  crumbs,
}: {
  product: ProductDetail;
  crumbs: { label: string; href: string }[];
}) {
  const productLd: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
  };
  if (product.brand) productLd.brand = { "@type": "Brand", name: product.brand };
  if (product.images.length) productLd.image = product.images.map((i) => i.url);
  if (product.description) productLd.description = product.description;
  if (product.price.final != null) {
    productLd.offers = {
      "@type": "Offer",
      price: product.price.final,
      priceCurrency: product.price.currency,
      availability:
        product.stock === "out"
          ? "https://schema.org/OutOfStock"
          : "https://schema.org/InStock",
    };
  }

  // Крошки + сам товар последним элементом цепочки.
  const items = [...crumbs, { label: product.name, href: `/product/${product.slug}` }];
  const breadcrumbLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.label,
      item: c.href,
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify([productLd, breadcrumbLd]) }}
    />
  );
}
