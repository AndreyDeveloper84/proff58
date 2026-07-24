import Image from "next/image";
import Link from "next/link";
import {
  Clock,
  Cog,
  Mail,
  MapPin,
  MessageSquareText,
  Phone,
  QrCode,
} from "lucide-react";
import { resolveStorefront, SITE, type ResolvedStorefront } from "@/lib/site";

// Компактный подвал по макету. Состав навигации намеренно определяется только
// существующими маршрутами — отсутствующие backend-разделы не подменяются "#".
// Стили — только семантические токены (globals.css); литеральный цвет оставлен
// лишь у чужого бренда (фиолетовый MAX).
export function Footer({
  logoUrl,
  siteName = SITE.brand.name,
  storefront = resolveStorefront(),
}: {
  logoUrl?: string;
  siteName?: string;
  storefront?: ResolvedStorefront;
}) {
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto grid max-w-[1400px] grid-cols-1 gap-6 px-4 py-6 sm:grid-cols-2 lg:grid-cols-[1.35fr_1.05fr_.9fr_.85fr_1.05fr_1.05fr]">
        {/* Левый блок: лого + описание */}
        <div>
          <span className="flex items-center gap-2">
            {logoUrl ? (
              <Image
                src={logoUrl}
                alt=""
                width={34}
                height={34}
                className="h-8 w-auto shrink-0 object-contain"
                aria-hidden
              />
            ) : (
              <Cog className="h-8 w-8 shrink-0 text-accent" strokeWidth={3} aria-hidden />
            )}
            <span className="flex flex-col leading-none">
              <span className="font-sans text-sm font-extrabold uppercase tracking-wide text-ink">
                {siteName}
              </span>
              <span className="mt-0.5 text-[9px] font-medium uppercase text-ink-3">
                {SITE.header.tagline}
              </span>
            </span>
          </span>
          <p className="mt-2 max-w-[260px] text-[11px] leading-[1.4] text-ink-2">
            {SITE.footerAbout}
          </p>
          {/* Кнопки соцсетей удалены по решению команды: реальных аккаунтов нет,
              ссылки вели на главные страницы сервисов. Вернуть вместе с адресами. */}
        </div>

        {/* Группы ссылок */}
        {SITE.footerColumns.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <h2 className="mb-2 font-sans text-xs font-bold text-ink">{col.title}</h2>
            <ul className="space-y-1 text-[11px] leading-[1.35]">
              {col.links.map((l) => (
                <li key={l.label} className="leading-[1.35]">
                  <Link href={l.href} className="text-ink-2 hover:text-accent">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}

        {/* Контакты + «Мы в мессенджерах» */}
        <div>
          <h2 className="mb-2 font-sans text-xs font-bold text-ink">Контакты</h2>
          <ul className="space-y-1.5 text-[11px] text-ink-2">
            <li className="flex items-center gap-2">
              <MapPin className="h-3.5 w-3.5 shrink-0 text-ink-2" aria-hidden />
              {storefront.address}
            </li>
            <li>
              <a href={storefront.phone.href} className="flex items-center gap-2 hover:text-accent">
                <Phone className="h-3.5 w-3.5 shrink-0 text-accent" aria-hidden />
                {storefront.phone.display}
              </a>
            </li>
            <li>
              <a href={`mailto:${storefront.email}`} className="flex items-center gap-2 hover:text-accent">
                <Mail className="h-3.5 w-3.5 shrink-0 text-ink-2" aria-hidden />
                {storefront.email}
              </a>
            </li>
            <li className="flex items-center gap-2">
              <Clock className="h-3.5 w-3.5 shrink-0 text-ink-2" aria-hidden />
              {storefront.schedule}
            </li>
          </ul>
        </div>

        <div>
          <a
            href={storefront.maxHref}
            target="_blank"
            rel="noopener noreferrer"
            data-event="footer_max"
            className="flex items-center gap-3 rounded-sm border border-line bg-surface p-2.5 transition hover:border-[#6156f5]"
          >
            <span className="grid h-14 w-14 shrink-0 place-items-center rounded-sm border border-line bg-surface text-ink-2">
              <QrCode className="h-9 w-9" strokeWidth={1.5} aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-ink">
                <MessageSquareText className="h-3.5 w-3.5 text-[#6156f5]" aria-hidden />
                Мы в мессенджерах
              </span>
              <span className="mt-0.5 block text-[11px] leading-snug text-ink-2">
                Напишите нам в MAX для консультации
              </span>
            </span>
          </a>
        </div>
      </div>

      {/* Нижняя строка. Политика/соглашение появятся вместе с юр. страницами —
          битые ссылки не рисуем (#591). */}
      <div className="border-t border-line">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-2 px-4 py-3 text-[11px] text-ink-3 sm:flex-row sm:items-center sm:justify-between">
          <span>© 2014–2026 {siteName}. Все права защищены.</span>
          <div className="flex flex-wrap gap-3">
            {SITE.payments.map((p) => (
              <span key={p}>{p}</span>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}
