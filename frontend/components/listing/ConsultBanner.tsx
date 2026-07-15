import { MessageSquareText } from "lucide-react";
import { SITE } from "@/lib/site";

// Блок консультации в MAX на страницах каталога (§помощь с выбором) — по макету:
// светлая карточка с рамкой, иконка чата, текст, тёмная кнопка «Спросить в MAX» и
// зелёный лого-квадрат MAX справа. Тексты/ссылка — из SITE.support.max.
export function ConsultBanner() {
  const { title, text, ctaLabel, href } = SITE.support.max;
  return (
    <section className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-line bg-raised px-5 py-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-surface text-ink-2">
        <MessageSquareText className="h-5 w-5" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="font-semibold text-ink">{title}</p>
        <p className="text-sm text-ink-2">{text}</p>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          data-event="consult_max_click"
          data-surface="plp"
          className="inline-flex h-11 items-center gap-2 rounded-md bg-header px-5 text-sm font-semibold text-header-ink transition hover:brightness-125 motion-reduce:transition-none"
        >
          {ctaLabel}
        </a>
        {/* Лого-квадрат MAX (фирменный зелёный). */}
        <span
          aria-hidden
          className="hidden h-11 w-11 shrink-0 place-items-center rounded-lg bg-accent font-display text-sm font-bold tracking-tight text-accent-ink sm:grid"
        >
          MAX
        </span>
      </div>
    </section>
  );
}
