import { CheckCircle2, MapPin, Truck, Users, Wrench } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HOME_CONTENT } from "@/lib/home-content";

// #588: сервисная полоса преимуществ под сценарными карточками.
const ICONS: Record<string, LucideIcon> = { MapPin, Truck, Users, CheckCircle2, Wrench };

export function HomeServiceStrip() {
  return (
    <section className="bg-canvas" aria-label="Преимущества магазина">
      <div className="mx-auto max-w-[1400px] px-4 pb-8 lg:pb-10">
        <div className="grid grid-cols-1 divide-y divide-line rounded-lg border border-line bg-surface sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-5 lg:divide-x">
          {HOME_CONTENT.serviceStrip.map((s) => {
            const Icon = ICONS[s.icon] ?? MapPin;
            return (
              <div key={s.title} className="flex items-center gap-3 p-4">
                <Icon className="h-6 w-6 shrink-0 text-accent" aria-hidden />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink">{s.title}</p>
                  <p className="text-xs text-ink-2">{s.text}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
