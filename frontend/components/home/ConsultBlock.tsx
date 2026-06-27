"use client";

import { MessageSquareText, Wrench } from "lucide-react";
import { Parallax } from "@/components/motion/Parallax";
import { HOME_CONTENT } from "@/lib/home-content";

type ConsultBlockProps = { onConsult: () => void };

export function ConsultBlock({ onConsult }: ConsultBlockProps) {
  const c = HOME_CONTENT.consult;
  return (
    <section className="relative overflow-hidden border-y border-line">
      {/* Параллакс-фон (плейсхолдер-градиент до фото дизайнера) */}
      <Parallax speed={50} className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[linear-gradient(120deg,rgba(14,17,19,0.96),rgba(30,34,38,0.7))]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_85%_50%,rgba(0,161,75,0.22),transparent_55%)]" />
      </Parallax>

      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="max-w-2xl">
          <h2 className="font-display text-2xl font-semibold uppercase tracking-wide text-ink sm:text-3xl">
            {c.title}
          </h2>
          <p className="mt-3 text-ink-2">{c.text}</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onConsult}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-5 py-3 text-sm font-semibold text-accent-ink transition hover:brightness-110"
            >
              <Wrench className="h-4 w-4" aria-hidden />
              Подобрать инструмент
            </button>
            <a
              href={c.maxUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-5 py-3 text-sm font-semibold text-ink transition hover:bg-raised"
            >
              <MessageSquareText className="h-4 w-4" aria-hidden />
              Консультация в MAX
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
