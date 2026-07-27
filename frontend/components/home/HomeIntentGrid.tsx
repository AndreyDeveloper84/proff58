import Link from "next/link";
import {
  ArrowRight,
  Briefcase,
  Cog,
  Hammer,
  Home,
  Paintbrush,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HOME_CONTENT } from "@/lib/home-content";

// #588: сценарный вход «Что вы хотите сделать?» — карточки по задаче покупателя.
const ICONS: Record<string, LucideIcon> = { Home, Paintbrush, Hammer, Briefcase, Cog };
const ICON_STYLES = [
  "text-[#9bc43c]",
  "text-[#0c8492]",
  "text-[#ff9200]",
  "text-[#777]",
  "text-[#5279aa]",
];

export function HomeIntentGrid() {
  const { title, cards } = HOME_CONTENT.intent;
  return (
    <section className="bg-surface" aria-labelledby="intent-title">
      <div className="mx-auto max-w-[1400px] px-4 pt-3.5">
        <h2
          id="intent-title"
          className="mb-2 font-sans text-lg font-bold text-ink"
        >
          {title}
        </h2>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
          {cards.map((c, index) => {
            const Icon = ICONS[c.icon] ?? Home;
            return (
              <Link
                key={c.title}
                href={c.href}
                className="group flex min-h-[72px] items-center gap-3 rounded-sm border border-line bg-surface px-3.5 py-2 transition hover:border-accent hover:shadow-sm"
              >
                <span className={`grid h-12 w-12 shrink-0 place-items-center ${ICON_STYLES[index]}`}>
                  <Icon className="h-9 w-9" strokeWidth={1.8} aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-bold leading-tight text-ink">{c.title}</span>
                    <ArrowRight
                      className="h-3.5 w-3.5 shrink-0 text-ink-2 transition group-hover:translate-x-0.5 group-hover:text-accent"
                      aria-hidden
                    />
                  </span>
                  <span className="mt-1 block text-[11px] leading-[1.3] text-ink-2">{c.text}</span>
                </span>
              </Link>
            );
          })}
        </div>
      </div>
    </section>
  );
}
