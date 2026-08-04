import {
  Award,
  BadgeRussianRuble,
  RotateCcw,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ARTICLES } from "@/lib/articles";
import { HOME_CONTENT } from "@/lib/home-content";
import { ArticlesCarousel } from "./ArticlesCarousel";

// #590: нижняя зона главной — «Почему покупают у нас» + статьи.
//
// Карточка e-mail-подписки убрана: рассылки в проекте нет и не планируется, а
// неактивная форма на витрине выглядела рабочей и молча ничего не делала.
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
      <ul className="grid grid-cols-1 items-stretch gap-2 sm:grid-cols-2 lg:grid-cols-6">
        {HOME_CONTENT.whyBuy.map((item) => {
          const Icon = WHY_ICONS[item.icon] ?? ShieldCheck;
          return (
            <li key={item.title} className="grid grid-cols-[28px_minmax(0,1fr)] items-start gap-2">
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

// Карточка MAX-помощи из правой колонки убрана: она дублировала подвал, который
// начинается сразу под ней («Мы в мессенджерах»).
export function HomeBottom() {
  return (
    <section className="bg-surface">
      <div className="mx-auto flex w-full max-w-[1680px] min-w-0 flex-col gap-2 px-4 pb-4 pt-2 sm:px-6 xl:px-8">
        <WhyBuyStrip />
        <ArticlesCarousel articles={ARTICLES} />
      </div>
    </section>
  );
}
