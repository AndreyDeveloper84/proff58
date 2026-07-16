import Image from "next/image";
import { MessageSquareText } from "lucide-react";

import { SITE } from "@/lib/site";
import { cn } from "@/lib/utils";

// Блок консультации в MAX (PLP-04): компактная горизонтальная карточка —
// иконка → текст → квадрат MAX. Вся карточка — одна доступная ссылка (без
// отдельной кнопки на всю ширину). Одинаковая версия на desktop и mobile.
export function ConsultBanner({ className }: { className?: string }) {
  const { title, text, href } = SITE.support.max;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      data-event="consult_max_click"
      data-surface="plp"
      aria-label={title}
      className={cn(
        "flex min-w-0 items-center gap-3 rounded-lg border border-line bg-raised p-3 transition hover:border-accent motion-reduce:transition-none",
        className,
      )}
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-surface text-ink-2">
        <MessageSquareText className="h-5 w-5" strokeWidth={1.75} aria-hidden />
      </span>

      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold leading-5 text-ink">{title}</p>
        <p className="mt-0.5 line-clamp-2 text-xs leading-4 text-ink-2">{text}</p>
      </div>

      {/* Чёрная кнопка с официальным цветным логотипом MAX. */}
      <span
        aria-hidden
        className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-header"
      >
        <Image
          src="/brands/max-colored.png"
          alt="MAX"
          width={28}
          height={28}
          className="h-7 w-7 object-contain"
        />
      </span>
    </a>
  );
}
