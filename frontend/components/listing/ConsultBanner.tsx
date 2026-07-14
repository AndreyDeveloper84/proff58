import { MessageSquareText } from "lucide-react";
import { SITE } from "@/lib/site";

// Блок консультации в MAX на страницах каталога (§помощь с выбором) — тот самый
// выделенный элемент из утверждённого макета. Презентационный: тексты/ссылка из SITE.support.
export function ConsultBanner() {
  const { title, text, ctaLabel, href } = SITE.support.max;
  return (
    <section className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-line bg-raised px-5 py-4">
      <MessageSquareText className="h-8 w-8 shrink-0 text-accent" strokeWidth={1.5} aria-hidden />
      <div className="min-w-0">
        <p className="font-medium text-ink">{title}</p>
        <p className="text-sm text-ink-2">{text}</p>
      </div>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        data-event="consult_max_click"
        data-surface="plp"
        className="ml-auto inline-flex items-center gap-2 rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition hover:opacity-90 motion-reduce:transition-none"
      >
        <MessageSquareText className="h-4 w-4" aria-hidden />
        {ctaLabel}
      </a>
    </section>
  );
}
