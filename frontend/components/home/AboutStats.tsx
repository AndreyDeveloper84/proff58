"use client";

import { Reveal } from "@/components/motion/Reveal";
import { HOME_CONTENT } from "@/lib/home-content";
import { StatCounter } from "./StatCounter";

export function AboutStats() {
  const a = HOME_CONTENT.about;
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <Reveal>
        <h2 className="font-display text-2xl font-semibold uppercase tracking-wide text-ink sm:text-3xl">
          {a.title}
        </h2>
        <p className="mt-3 max-w-2xl text-ink-2">{a.text}</p>
      </Reveal>
      <div className="mt-10 grid grid-cols-2 gap-6 sm:grid-cols-4">
        {a.stats.map((s) => (
          <StatCounter key={s.label} {...s} />
        ))}
      </div>
    </section>
  );
}
