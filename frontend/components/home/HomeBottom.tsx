import Image from "next/image";
import {
  Award,
  BadgeRussianRuble,
  MessageSquareText,
  RotateCcw,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ARTICLES } from "@/lib/articles";
import { HOME_CONTENT } from "@/lib/home-content";
import { SITE } from "@/lib/site";
import { ArticlesCarousel } from "./ArticlesCarousel";

// #590: нижняя зона главной по макету — «Почему покупают у нас» + статьи +
// email-подписка (левая колонка) и карточка MAX-помощи (правая колонка).
const WHY_ICONS: Record<string, LucideIcon> = {
  Award,
  ShieldCheck,
  Users,
  Wrench,
  BadgeRussianRuble,
  RotateCcw,
};

export function WhyBuyStrip() {
  return (
    <div className="rounded-sm border border-line bg-surface px-3 py-2.5" aria-label="Почему покупают у нас">
      <h2 className="mb-2 font-sans text-sm font-bold text-ink">
        Почему покупают у нас
      </h2>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-6">
        {HOME_CONTENT.whyBuy.map((item) => {
          const Icon = WHY_ICONS[item.icon] ?? ShieldCheck;
          return (
            <li key={item.title} className="flex items-start gap-2">
              <span className="grid h-7 w-7 shrink-0 place-items-center text-accent">
                <Icon className="h-5 w-5" strokeWidth={1.7} aria-hidden />
              </span>
              <span className="min-w-0">
                <span className="block text-[11px] font-bold leading-tight text-ink">{item.title}</span>
                <span className="block text-[10px] leading-[1.3] text-ink-2">{item.text}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function SubscribeCard() {
  const s = HOME_CONTENT.subscribe;
  return (
    <div
      className="relative overflow-hidden rounded-sm border border-line bg-surface px-4 py-3"
      aria-label={s.title}
    >
      <div
        aria-hidden
        className="absolute -right-3 top-1 h-14 w-28 rotate-[-8deg] rounded-[40%] bg-[linear-gradient(135deg,transparent_15%,rgba(94,195,205,.16)_16%,rgba(94,195,205,.16)_48%,transparent_49%)]"
      />
      <h2 className="relative font-sans text-sm font-bold text-ink">{s.title}</h2>
      <p className="relative mt-0.5 max-w-[360px] text-[11px] leading-[1.35] text-ink-2">{s.text}</p>
      {/* UI-заглушка (#590): backend рассылки нет — поле и кнопка неактивны,
          причина показана пользователю. Включим при появлении backend. */}
      <div className="relative mt-2 flex gap-2">
        <input
          type="email"
          placeholder="Ваш e-mail"
          disabled
          aria-label="E-mail для подписки"
          className="h-9 min-w-0 flex-1 rounded-sm border border-line bg-surface px-3 text-xs text-ink placeholder:text-ink-3 disabled:cursor-not-allowed"
        />
        <button
          type="button"
          disabled
          className="inline-flex h-9 shrink-0 items-center rounded-sm bg-accent px-4 text-xs font-semibold text-accent-ink disabled:cursor-not-allowed disabled:opacity-75"
        >
          {s.cta}
        </button>
      </div>
      <p className="sr-only">{s.note}</p>
    </div>
  );
}

function MaxHelpCard({ maxHref }: { maxHref: string }) {
  const m = HOME_CONTENT.maxHelp;
  return (
    <div
      className="flex h-full min-h-[150px] flex-col justify-between rounded-sm border border-line bg-[linear-gradient(135deg,var(--surface)_0%,var(--max-tint)_100%)] p-3.5"
      aria-label={m.title}
    >
      <div className="relative pr-14">
        <Image
          src="/brands/max-colored.png"
          alt=""
          width={58}
          height={58}
          className="absolute right-0 top-0 h-12 w-12 object-contain"
          aria-hidden
        />
        <h2 className="font-sans text-sm font-bold leading-tight text-ink">{m.title}</h2>
        <p className="mt-1 text-[11px] leading-[1.35] text-ink-2">{m.text}</p>
      </div>
      <a
        href={maxHref}
        target="_blank"
        rel="noopener noreferrer"
        data-event="home_max_help"
        className="mt-2.5 inline-flex h-9 items-center justify-center gap-1.5 self-start rounded-sm bg-[#6156f5] px-3 text-xs font-semibold text-white transition hover:bg-[#5147dc]"
      >
        <MessageSquareText className="h-4 w-4" aria-hidden />
        {m.cta}
      </a>
    </div>
  );
}

export function HomeBottom({ maxHref = SITE.support.max.href }: { maxHref?: string } = {}) {
  return (
    <section className="bg-surface">
      <div className="mx-auto max-w-[1400px] px-4 pb-2.5 pt-2">
        <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="flex min-w-0 flex-col gap-1.5">
            <WhyBuyStrip />
            <div className="grid grid-cols-1 gap-2.5 xl:grid-cols-[minmax(0,1fr)_360px]">
              <ArticlesCarousel articles={ARTICLES} />
              <SubscribeCard />
            </div>
          </div>
          <MaxHelpCard maxHref={maxHref} />
        </div>
      </div>
    </section>
  );
}
