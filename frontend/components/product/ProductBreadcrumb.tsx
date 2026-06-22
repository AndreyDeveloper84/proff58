import { ChevronRight } from "lucide-react";

type Crumb = { name: string; slug: string };

export function ProductBreadcrumb({
  breadcrumb,
  productName,
}: {
  breadcrumb: Crumb[];
  productName: string;
}) {
  return (
    <nav aria-label="Хлебные крошки">
      <ol className="flex flex-wrap items-center gap-1 text-xs text-ink-3">
        <li>
          <a href="/" className="transition-colors hover:text-accent">
            Главная
          </a>
        </li>

        {breadcrumb.map((crumb) => (
          <li key={crumb.slug} className="flex items-center gap-1">
            <ChevronRight className="h-3 w-3 shrink-0" aria-hidden />
            <a
              href={`/catalog/${crumb.slug}`}
              className="transition-colors hover:text-accent"
            >
              {crumb.name}
            </a>
          </li>
        ))}

        <li className="flex items-center gap-1">
          <ChevronRight className="h-3 w-3 shrink-0" aria-hidden />
          <span className="text-ink-2">{productName}</span>
        </li>
      </ol>
    </nav>
  );
}
