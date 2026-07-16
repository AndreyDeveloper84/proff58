import { MessageSquareText } from "lucide-react";

import { SITE } from "@/lib/site";
import { cn } from "@/lib/utils";

// Блок консультации в MAX — вертикальная карточка для левой колонки PLP (шириной
// с фильтры). Иконка чата + текст, кнопка на всю ширину; отдельного квадрата MAX нет.
export function ConsultBanner({ className }: { className?: string }) {
  const { title, text, ctaLabel, href } = SITE.support.max;

  return (
    <section
      className={cn(
        "flex min-w-0 flex-col rounded-lg border border-line bg-raised p-4",
        className,
      )}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface text-ink-2">
          <MessageSquareText className="h-5 w-5" strokeWidth={1.75} aria-hidden />
        </span>

        <div className="min-w-0">
          <p className="text-sm font-semibold leading-5 text-ink">{title}</p>
          <p className="mt-0.5 text-xs leading-5 text-ink-2">{text}</p>
        </div>
      </div>

      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        data-event="consult_max_click"
        data-surface="plp"
        className="mt-3 inline-flex h-11 w-full items-center justify-center rounded-md bg-header px-4 text-center text-sm font-semibold text-header-ink transition hover:brightness-125 motion-reduce:transition-none"
      >
        {ctaLabel}
      </a>
    </section>
  );
}
