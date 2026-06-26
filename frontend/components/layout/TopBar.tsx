import Link from "next/link";
import { MapPin, Phone, Clock, Heart, GitCompare, User } from "lucide-react";
import { SITE } from "@/lib/site";

// Верхняя инфо-панель шапки. Иконки «Избранное»/«Сравнение» — визуальные
// (без перехода): рабочих роутов нет, persistence — отдельная задача (P2).
export function TopBar() {
  return (
    <div className="border-b border-line bg-surface text-xs text-ink-3">
      <div className="mx-auto flex h-9 max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-8">
        <span className="hidden items-center gap-1 sm:flex">
          <MapPin className="h-3.5 w-3.5 text-accent" aria-hidden />
          {SITE.region}
        </span>

        <nav aria-label="Информация" className="hidden gap-4 md:flex">
          {SITE.topNav.map((l) => (
            <Link key={l.label} href={l.href} className="hover:text-accent">
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <a href={SITE.phone.href} className="flex items-center gap-1 font-medium text-ink hover:text-accent">
            <Phone className="h-3.5 w-3.5 text-accent" aria-hidden />
            {SITE.phone.display}
          </a>
          <span className="hidden items-center gap-1 lg:flex">
            <Clock className="h-3.5 w-3.5" aria-hidden />
            {SITE.schedule}
          </span>

          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="Избранное"
              title="Избранное"
              className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:text-accent"
            >
              <Heart className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Сравнение"
              title="Сравнение"
              className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:text-accent"
            >
              <GitCompare className="h-4 w-4" aria-hidden />
            </button>
            <Link
              href="/account"
              aria-label="Вход в личный кабинет"
              title="Вход в личный кабинет"
              className="grid h-7 w-7 place-items-center rounded-md text-ink-3 hover:text-accent"
            >
              <User className="h-4 w-4" aria-hidden />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
