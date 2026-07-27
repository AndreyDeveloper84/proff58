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

export function HomeIntentGrid() {
  const { title, cards } = HOME_CONTENT.intent;
  return (
    <section className="bg-canvas" aria-labelledby="intent-title">
      <div className="mx-auto max-w-[1400px] px-4 py-8 lg:py-10">
        <h2
          id="intent-title"
          className="mb-5 font-display text-2xl font-bold text-ink sm:text-3xl"
        >
          {title}
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {cards.map((c) => {
            const Icon = ICONS[c.icon] ?? Home;
            return (
              <Link
                key={c.title}
                href={c.href}
                className="group flex items-start gap-3 rounded-lg border border-line bg-surface p-4 transition hover:-translate-y-0.5 hover:border-accent hover:shadow-sm"
              >
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-md bg-accent/10 text-accent">
                  <Icon className="h-6 w-6" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-ink">{c.title}</span>
                    <ArrowRight
                      className="h-4 w-4 shrink-0 text-ink-3 transition group-hover:translate-x-0.5 group-hover:text-accent"
                      aria-hidden
                    />
                  </span>
                  <span className="mt-1 block text-xs leading-relaxed text-ink-2">{c.text}</span>
                </span>
              </Link>
            );
          })}
        </div>
      </div>
    </section>
  );
}
