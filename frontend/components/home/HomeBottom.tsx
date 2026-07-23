import {
  Award,
  BadgeRussianRuble,
  CalendarDays,
  MessageSquareText,
  Newspaper,
  RotateCcw,
  Send,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HOME_CONTENT } from "@/lib/home-content";
import { SITE } from "@/lib/site";

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

function WhyBuyStrip() {
  return (
    <div className="rounded-lg border border-line bg-surface p-5" aria-label="Почему покупают у нас">
      <h2 className="mb-4 font-display text-xl font-bold text-ink sm:text-2xl">
        Почему покупают у нас
      </h2>
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {HOME_CONTENT.whyBuy.map((item) => {
          const Icon = WHY_ICONS[item.icon] ?? ShieldCheck;
          return (
            <li key={item.title} className="flex items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-accent/10 text-accent">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-ink">{item.title}</span>
                <span className="block text-xs leading-relaxed text-ink-2">{item.text}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ArticlesPreview() {
  const a = HOME_CONTENT.articles;
  return (
    <div className="rounded-lg border border-line bg-surface p-5" aria-label={a.title}>
      {/* «Читать все статьи» намеренно отсутствует: раздела статей на сайте нет,
          битую ссылку не рисуем (появится раздел — добавим ссылку и кликабельность). */}
      <h2 className="mb-4 font-display text-xl font-bold text-ink sm:text-2xl">{a.title}</h2>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {a.items.map((item) => (
          <li
            key={item.title}
            className="flex items-start gap-3 rounded-md border border-line bg-canvas p-3"
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-raised text-ink-3">
              <Newspaper className="h-5 w-5" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium leading-snug text-ink">{item.title}</span>
              <span className="mt-1 flex items-center gap-1 text-xs text-ink-3">
                <CalendarDays className="h-3.5 w-3.5" aria-hidden />
                {item.date}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SubscribeCard() {
  const s = HOME_CONTENT.subscribe;
  return (
    <div className="rounded-lg border border-line bg-surface p-5" aria-label={s.title}>
      <h2 className="font-display text-lg font-bold text-ink">{s.title}</h2>
      <p className="mt-1 text-xs leading-relaxed text-ink-2">{s.text}</p>
      {/* UI-заглушка (#590): backend рассылки нет — поле и кнопка неактивны,
          причина показана пользователю. Включим при появлении backend. */}
      <div className="mt-3 flex gap-2">
        <input
          type="email"
          placeholder="Ваш e-mail"
          disabled
          aria-label="E-mail для подписки"
          className="h-11 min-w-0 flex-1 rounded-md border border-line bg-raised px-3 text-sm text-ink placeholder:text-ink-3 disabled:cursor-not-allowed disabled:opacity-60 sm:h-10"
        />
        <button
          type="button"
          disabled
          className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink disabled:cursor-not-allowed disabled:opacity-60 sm:h-10"
        >
          <Send className="h-4 w-4" aria-hidden />
          {s.cta}
        </button>
      </div>
      <p className="mt-2 text-[11px] text-ink-3">{s.note}</p>
    </div>
  );
}

function MaxHelpCard() {
  const m = HOME_CONTENT.maxHelp;
  return (
    <div
      className="flex h-full flex-col justify-between rounded-lg border border-line bg-surface p-5"
      aria-label={m.title}
    >
      <div>
        <span className="grid h-14 w-14 place-items-center rounded-full bg-accent/10">
          <MessageSquareText className="h-7 w-7 text-accent" aria-hidden />
        </span>
        <h2 className="mt-4 font-display text-xl font-bold text-ink">{m.title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">{m.text}</p>
      </div>
      <a
        href={SITE.support.max.href}
        target="_blank"
        rel="noopener noreferrer"
        data-event="home_max_help"
        className="mt-5 inline-flex h-11 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink transition hover:brightness-110"
      >
        <MessageSquareText className="h-4 w-4" aria-hidden />
        {m.cta}
      </a>
    </div>
  );
}

export function HomeBottom() {
  return (
    <section className="bg-canvas">
      <div className="mx-auto max-w-[1400px] px-4 pb-10 lg:pb-14">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="flex flex-col gap-4">
            <WhyBuyStrip />
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
              <ArticlesPreview />
              <SubscribeCard />
            </div>
          </div>
          <MaxHelpCard />
        </div>
      </div>
    </section>
  );
}
