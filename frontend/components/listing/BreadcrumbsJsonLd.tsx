import { serializeJsonLd } from "@/lib/jsonld";

/**
 * Микроразметка хлебных крошек раздела каталога.
 *
 * У карточки товара такая разметка была с самого начала (ProductJsonLd), а у
 * разделов — нет: поисковик видел ссылку на «Уровни» без понимания, что она
 * лежит внутри «Измерительного инструмента», и в выдаче путь не показывался.
 */
export function BreadcrumbsJsonLd({
  crumbs,
}: {
  crumbs: { label: string; href: string }[];
}) {
  if (crumbs.length === 0) return null;
  const data = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.label,
      item: crumb.href,
    })),
  };
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: serializeJsonLd(data) }}
    />
  );
}
