import Link from "next/link";
import {
  ShieldCheck,
  Truck,
  Undo2,
  Wrench,
  Gift,
  Phone,
  Mail,
  MapPin,
  Clock,
  Send,
  Play,
  type LucideIcon,
} from "lucide-react";
import { SITE } from "@/lib/site";

// Маппинг строковых ключей конфига в иконки (lib/site.ts — без JSX).
const TRUST_ICONS: Record<string, LucideIcon> = {
  shield: ShieldCheck,
  truck: Truck,
  undo: Undo2,
  wrench: Wrench,
  gift: Gift,
};
const SOCIAL_ICONS: Record<string, LucideIcon> = {
  telegram: Send,
  youtube: Play, // у lucide нет бренд-иконки YouTube → play-заглушка
  vk: Send, // у lucide нет бренд-иконки VK → нейтральная заглушка
};

export function Footer() {
  return (
    <footer className="mt-12 border-t border-line bg-surface">
      {/* Trust-бейджи */}
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-4 px-4 py-6 sm:grid-cols-3 lg:grid-cols-5 sm:px-6 lg:px-8">
        {SITE.trustBadges.map((b) => {
          const Icon = TRUST_ICONS[b.icon] ?? ShieldCheck;
          return (
            <div key={b.label} className="flex items-center gap-2 text-sm text-ink-2">
              <Icon className="h-5 w-5 shrink-0 text-accent" aria-hidden />
              {b.label}
            </div>
          );
        })}
      </div>

      <div className="border-t border-line">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-8 px-4 py-8 md:grid-cols-4 sm:px-6 lg:px-8">
          {/* Колонки ссылок */}
          {SITE.footerColumns.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <h3 className="mb-3 font-display text-sm font-semibold uppercase tracking-wide text-ink">
                {col.title}
              </h3>
              <ul className="space-y-2">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="text-sm text-ink-2 hover:text-accent">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}

          {/* Колонка контактов */}
          <div>
            <h3 className="mb-3 font-display text-sm font-semibold uppercase tracking-wide text-ink">
              Контакты
            </h3>
            <ul className="space-y-2 text-sm text-ink-2">
              <li>
                <a href={SITE.phone.href} className="flex items-center gap-2 hover:text-accent">
                  <Phone className="h-4 w-4 shrink-0 text-accent" aria-hidden />
                  {SITE.phone.display}
                </a>
              </li>
              <li className="flex items-center gap-2">
                <Clock className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                {SITE.schedule}
              </li>
              <li>
                <a href={`mailto:${SITE.email}`} className="flex items-center gap-2 hover:text-accent">
                  <Mail className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                  {SITE.email}
                </a>
              </li>
              <li className="flex items-center gap-2">
                <MapPin className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                {SITE.address}
              </li>
            </ul>
            {/* Соцсети */}
            <div className="mt-4 flex gap-2">
              {SITE.socials.map((s) => {
                const Icon = SOCIAL_ICONS[s.icon] ?? Send;
                return (
                  <a
                    key={s.label}
                    href={s.href}
                    aria-label={s.label}
                    className="grid h-9 w-9 place-items-center rounded-md border border-line text-ink-2 transition hover:border-accent hover:text-accent"
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                  </a>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Оплата + копирайт */}
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-5 text-xs text-ink-3 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <div className="flex flex-wrap gap-2">
            {SITE.payments.map((p) => (
              <span key={p} className="rounded-md border border-line bg-raised px-2 py-1">
                {p}
              </span>
            ))}
          </div>
          <span>
            © 2026 {SITE.brand.name} · {SITE.region}
          </span>
        </div>
      </div>
    </footer>
  );
}
