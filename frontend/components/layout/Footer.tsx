import Image from "next/image";
import Link from "next/link";
import {
  Clock,
  Mail,
  MapPin,
  MessageSquareText,
  Phone,
  Play,
  QrCode,
  Send,
  type LucideIcon,
} from "lucide-react";
import { SITE } from "@/lib/site";

// Маппинг строковых ключей конфига в иконки (lib/site.ts — без JSX).
const SOCIAL_ICONS: Record<string, LucideIcon> = {
  telegram: Send,
  youtube: Play, // у lucide нет бренд-иконки YouTube → play-заглушка
  vk: Send, // у lucide нет бренд-иконки VK → нейтральная заглушка
};

// #591: светлый навигационный подвал по утверждённому макету. Больше не «тёмная
// брендовая рамка»: класс dark снят, семантические токены следуют за темой сайта
// (светлый в светлой, тёмный в тёмной — как header, #586).
// Ссылки — только на существующие маршруты: инфо-страниц (/delivery, /about …)
// на сайте нет, битые href в подвале не рисуем (группы из макета появятся вместе
// со страницами; список скрытого — в MR #591).
export function Footer() {
  return (
    <footer className="mt-12 border-t border-line bg-surface">
      <div className="mx-auto grid max-w-[1400px] grid-cols-1 gap-8 px-4 py-10 sm:grid-cols-2 lg:grid-cols-[1.2fr_1fr_1fr_1fr_1.2fr]">
        {/* Левый блок: лого + описание + соцсети */}
        <div>
          <span className="flex items-center gap-2">
            <Image
              src="/brands/professional-mark.png"
              alt=""
              width={40}
              height={40}
              className="h-9 w-auto shrink-0 object-contain"
              aria-hidden
            />
            <span className="flex flex-col leading-none">
              <span className="font-display text-base font-bold uppercase tracking-wide text-ink">
                {SITE.brand.name}
              </span>
              <span className="mt-1 text-[10px] font-medium text-ink-3">
                {SITE.header.tagline}
              </span>
            </span>
          </span>
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-ink-2">{SITE.footerAbout}</p>
          <div className="mt-4 flex gap-2">
            {SITE.socials.map((s) => {
              const Icon = SOCIAL_ICONS[s.icon] ?? Send;
              return (
                <a
                  key={s.label}
                  href={s.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={s.label}
                  className="grid h-9 w-9 place-items-center rounded-md border border-line text-ink-2 transition hover:border-accent hover:text-accent"
                >
                  <Icon className="h-4 w-4" aria-hidden />
                </a>
              );
            })}
          </div>
        </div>

        {/* Группы ссылок */}
        {SITE.footerColumns.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wide text-ink">
              {col.title}
            </h2>
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

        {/* Контакты + «Мы в мессенджерах» */}
        <div>
          <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-wide text-ink">
            Контакты
          </h2>
          <ul className="space-y-2 text-sm text-ink-2">
            <li className="flex items-center gap-2">
              <MapPin className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
              {SITE.address}
            </li>
            <li>
              <a href={SITE.phone.href} className="flex items-center gap-2 hover:text-accent">
                <Phone className="h-4 w-4 shrink-0 text-accent" aria-hidden />
                {SITE.phone.display}
              </a>
            </li>
            <li>
              <a href={`mailto:${SITE.email}`} className="flex items-center gap-2 hover:text-accent">
                <Mail className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                {SITE.email}
              </a>
            </li>
            <li className="flex items-center gap-2">
              <Clock className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
              {SITE.schedule}
            </li>
          </ul>

          {/* #591: MAX/QR-карточка. Финального QR-ассета нет — placeholder-иконка,
              рабочая ссылка ведёт в MAX-канал. */}
          <a
            href={SITE.support.max.href}
            target="_blank"
            rel="noopener noreferrer"
            data-event="footer_max"
            className="mt-4 flex items-center gap-3 rounded-lg border border-line bg-canvas p-3 transition hover:border-accent"
          >
            <span className="grid h-14 w-14 shrink-0 place-items-center rounded-md border border-line bg-surface text-ink-3">
              <QrCode className="h-8 w-8" aria-hidden />
            </span>
            <span className="min-w-0 text-sm">
              <span className="flex items-center gap-1.5 font-semibold text-ink">
                <MessageSquareText className="h-4 w-4 text-accent" aria-hidden />
                Мы в мессенджерах
              </span>
              <span className="mt-0.5 block text-xs leading-snug text-ink-2">
                Напишите нам в MAX для консультации
              </span>
            </span>
          </a>
        </div>
      </div>

      {/* Нижняя строка. Политика/соглашение появятся вместе с юр. страницами —
          битые ссылки не рисуем (#591). */}
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-3 px-4 py-5 text-xs text-ink-3 sm:flex-row sm:items-center sm:justify-between">
          <span>
            © 2014–2026 {SITE.brand.name}. Все права защищены.
          </span>
          <div className="flex flex-wrap gap-2">
            {SITE.payments.map((p) => (
              <span key={p} className="rounded-md border border-line bg-raised px-2 py-1">
                {p}
              </span>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}
