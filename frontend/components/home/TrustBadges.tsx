"use client";

import { Building2, ShieldCheck, Store, Truck, Wrench } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Reveal } from "@/components/motion/Reveal";
import { HOME_CONTENT } from "@/lib/home-content";

const ICONS: Record<string, LucideIcon> = {
  ShieldCheck,
  Truck,
  Store,
  Wrench,
  Building2,
};

export function TrustBadges() {
  return (
    <section className="border-y border-line bg-surface">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Reveal>
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {HOME_CONTENT.trust.map((item) => {
              const Icon = ICONS[item.icon] ?? ShieldCheck;
              return (
                <li key={item.title} className="flex items-center gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-raised text-brand">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <span className="text-sm text-ink-2">{item.title}</span>
                </li>
              );
            })}
          </ul>
        </Reveal>
      </div>
    </section>
  );
}
