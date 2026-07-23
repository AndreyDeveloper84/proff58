"use client";

import Link from "next/link";
import {
  ArrowRight,
  MessageSquareText,
  ShieldCheck,
  Truck,
  Users,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HOME_CONTENT } from "@/lib/home-content";
import { SITE } from "@/lib/site";

type HeroProps = { onConsult: () => void };

const BULLET_ICONS: Record<string, LucideIcon> = {
  ShieldCheck,
  Truck,
  Users,
  Wrench,
};

// #587: первый экран главной — широкий тёмный фотобаннер (утверждённый макет).
// Баннер всегда тёмный (это «фото»), поэтому его корень несёт класс `dark`:
// семантические токены внутри резолвятся в тёмные значения, текст/CTA остаются
// токен-driven в обеих темах сайта. Фон — индустриальный градиент-плейсхолдер
// до финального фото инструментов (заменить на next/image в public/home/hero).
export function Hero({ onConsult }: HeroProps) {
  const h = HOME_CONTENT.hero;
  return (
    <section className="bg-canvas">
      <div className="mx-auto max-w-[1400px] px-4 py-6 lg:py-8">
        <div className="dark relative overflow-hidden rounded-2xl border border-header-line bg-header">
          {/* Плейсхолдер «фото»: тёмный индустриальный градиент с зелёным свечением
              справа. Заменить финальным ассетом (public/home/hero/*) через next/image. */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_120%_at_82%_28%,rgba(11,138,67,0.28),transparent_55%),linear-gradient(120deg,#0e1216_0%,#12181d_45%,#1a232a_100%)]"
          />
          <div className="relative grid items-center gap-8 p-6 sm:p-10 lg:grid-cols-[1.05fr_0.95fr] lg:p-14">
            <div className="max-w-xl">
              <h1 className="font-display text-3xl font-bold leading-tight text-ink sm:text-4xl lg:text-5xl">
                {h.titleLine1}
              </h1>
              <p className="mt-1 font-display text-2xl font-bold leading-tight text-accent sm:text-3xl">
                {h.titleLine2}
              </p>
              <p className="mt-4 max-w-lg text-sm leading-relaxed text-ink-2 sm:text-base">
                {h.subtitle}
              </p>

              <ul className="mt-6 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
                {h.bullets.map((b) => {
                  const Icon = BULLET_ICONS[b.icon] ?? ShieldCheck;
                  return (
                    <li key={b.text} className="flex items-center gap-2.5 text-sm text-ink-2">
                      <Icon className="h-5 w-5 shrink-0 text-accent" aria-hidden />
                      {b.text}
                    </li>
                  );
                })}
              </ul>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <button
                  type="button"
                  onClick={onConsult}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-accent px-6 text-sm font-semibold text-accent-ink transition hover:brightness-110"
                >
                  {h.primaryCta.label}
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </button>
                <Link
                  href={h.secondaryCta.href}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-md border border-line bg-surface px-6 text-sm font-semibold text-ink transition hover:bg-raised"
                >
                  {h.secondaryCta.label}
                </Link>
              </div>

              <a
                href={SITE.support.max.href}
                target="_blank"
                rel="noopener noreferrer"
                data-event="hero_consult_max"
                className="mt-4 inline-flex items-center gap-2 rounded-pill border border-line bg-surface/60 px-4 py-2 text-xs text-ink-2 transition hover:border-accent hover:text-ink"
              >
                <MessageSquareText className="h-4 w-4 shrink-0 text-accent" aria-hidden />
                <span className="font-semibold text-ink">{h.maxPill.title}</span>
                <span className="hidden sm:inline">— {h.maxPill.note}</span>
              </a>
            </div>

            {/* Правая зона под фото инструментов — плейсхолдер до ассета. */}
            <div
              aria-hidden
              className="hidden aspect-[4/3] w-full rounded-xl border border-header-line bg-[radial-gradient(circle_at_50%_45%,rgba(11,138,67,0.16),rgba(14,18,22,0.65))] lg:block"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
