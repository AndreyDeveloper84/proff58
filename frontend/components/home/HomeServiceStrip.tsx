import { CheckCircle2, MapPin, Truck, Users, Wrench } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HOME_CONTENT } from "@/lib/home-content";

// #588: сервисная полоса преимуществ под сценарными карточками.
const ICONS: Record<string, LucideIcon> = { MapPin, Truck, Users, CheckCircle2, Wrench };

export function HomeServiceStrip() {
  return (
    <section className="bg-surface" aria-label="Преимущества магазина">
      <div className="mx-auto max-w-[1400px] px-4 pt-2">
        <div className="grid grid-cols-1 divide-y divide-line rounded-sm border border-line bg-surface sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-5 lg:divide-x">
          {HOME_CONTENT.serviceStrip.map((s) => {
            const Icon = ICONS[s.icon] ?? MapPin;
            return (
              <div key={s.title} className="flex min-h-[46px] items-center justify-center gap-2 px-3 py-2">
                <Icon className="h-5 w-5 shrink-0 text-ink-2" strokeWidth={1.7} aria-hidden />
                <div className="min-w-0">
                  <p className="text-xs font-bold leading-tight text-ink">{s.title}</p>
                  <p className="text-[11px] leading-tight text-ink-2">{s.text}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
