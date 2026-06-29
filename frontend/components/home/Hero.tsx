"use client";

import Link from "next/link";
import { ArrowRight, MessageSquareText } from "lucide-react";
import { Parallax } from "@/components/motion/Parallax";
import { HOME_CONTENT } from "@/lib/home-content";

type HeroProps = { onConsult: () => void };

export function Hero({ onConsult }: HeroProps) {
  const h = HOME_CONTENT.hero;
  return (
    <section className="relative overflow-hidden bg-canvas">
      {/* Слой 1 — дальний фон */}
      <Parallax speed={40} className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_30%,rgba(0,161,75,0.18),transparent_55%)]" />
      </Parallax>
      {/* Слой 2 — средний (декоративный градиент) */}
      <Parallax speed={-30} className="pointer-events-none absolute inset-0 -z-10 opacity-40">
        <div className="absolute right-0 top-0 h-full w-2/3 bg-[linear-gradient(115deg,transparent,rgba(181,230,29,0.08))]" />
      </Parallax>

      <div className="mx-auto grid max-w-7xl items-center gap-8 px-4 py-16 sm:px-6 md:grid-cols-2 md:py-24 lg:px-8">
        {/* Слой 5 — текст/CTA (всегда поверх, самый «быстрый») */}
        <div className="relative z-10 max-w-xl">
          <h1 className="font-display text-4xl font-bold uppercase leading-tight tracking-wide text-ink sm:text-5xl">
            {h.titleLine1}
          </h1>
          <p className="mt-2 font-display text-xl text-accent sm:text-2xl">{h.titleLine2}</p>
          <ul className="mt-6 space-y-2 text-sm text-ink-2">
            {h.bullets.map((b) => (
              <li key={b} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
                {b}
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href={h.primaryCta.href}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-5 py-3 text-sm font-semibold text-accent-ink transition hover:brightness-110"
            >
              {h.primaryCta.label}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
            <button
              type="button"
              onClick={onConsult}
              className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-5 py-3 text-sm font-semibold text-ink transition hover:bg-raised"
            >
              <MessageSquareText className="h-4 w-4" aria-hidden />
              Получить консультацию
            </button>
          </div>
        </div>

        {/* Слой 4 — объект (фото-инструмент); плейсхолдер до ассета дизайнера */}
        <Parallax speed={-50} className="relative z-0 hidden md:block">
          <div className="aspect-square w-full rounded-lg border border-line bg-[radial-gradient(circle_at_50%_40%,rgba(181,230,29,0.12),rgba(30,34,38,0.9))]" />
        </Parallax>
      </div>
    </section>
  );
}
