"use client";

import Image from "next/image";
import Link from "next/link";
import {
  MessageSquareText,
  ShieldCheck,
  Truck,
  Users,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HOME_CONTENT } from "@/lib/home-content";
import { SITE } from "@/lib/site";

type HeroProps = { onConsult: () => void; maxHref?: string };

const BULLET_ICONS: Record<string, LucideIcon> = {
  ShieldCheck,
  Truck,
  Users,
  Wrench,
};

// Первый экран по утверждённому макету. Текст и действия остаются HTML, а
// сгенерированная фотография используется только как декоративный фон.
export function Hero({ onConsult, maxHref = SITE.support.max.href }: HeroProps) {
  const h = HOME_CONTENT.hero;
  return (
    <section className="bg-surface">
      <div className="mx-auto max-w-[1400px] px-4 pt-1.5">
        <div className="dark relative min-h-[300px] overflow-hidden rounded-md bg-header">
          <Image
            src="/home/hero/approved-tools-hero.png"
            alt=""
            fill
            priority
            sizes="(max-width: 768px) 100vw, 1400px"
            className="object-cover object-[62%_50%] opacity-95"
            aria-hidden
          />
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(5,8,10,.98)_0%,rgba(5,8,10,.91)_31%,rgba(5,8,10,.54)_51%,rgba(5,8,10,.08)_74%)]"
          />
          <div className="relative flex min-h-[300px] items-center px-5 py-6 sm:px-8 lg:px-12 lg:py-6">
            <div className="w-full max-w-[620px]">
              <h1 className="font-sans text-[29px] font-extrabold leading-[1.08] tracking-[-0.02em] text-white sm:text-[31px]">
                {h.titleLine1}
              </h1>
              <p className="mt-1 font-sans text-[22px] font-bold leading-tight text-white sm:text-[24px]">
                {h.titleLine2}
              </p>
              <p className="mt-3 max-w-[560px] text-sm leading-[1.45] text-white/80">
                {h.subtitle}
              </p>

              <ul className="mt-4 grid grid-cols-2 gap-y-3 sm:flex sm:items-center">
                {h.bullets.map((b) => {
                  const Icon = BULLET_ICONS[b.icon] ?? ShieldCheck;
                  return (
                    <li
                      key={b.text}
                      className="flex items-center gap-2 pr-3 text-xs leading-tight text-white/85 sm:border-r sm:border-white/20 sm:pl-3 sm:first:pl-0 sm:last:border-0"
                    >
                      <Icon className="h-5 w-5 shrink-0 text-accent" strokeWidth={1.7} aria-hidden />
                      <span className="max-w-[120px]">{b.text}</span>
                    </li>
                  );
                })}
              </ul>

              <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={onConsult}
                  className="inline-flex h-10 items-center justify-center rounded-sm bg-accent px-7 text-[13px] font-semibold text-accent-ink transition hover:brightness-110"
                >
                  {h.primaryCta.label}
                </button>
                <Link
                  href={h.secondaryCta.href}
                  className="inline-flex h-10 items-center justify-center rounded-sm border border-white/80 bg-white px-8 text-[13px] font-semibold text-[#202326] transition hover:bg-white/90"
                >
                  {h.secondaryCta.label}
                </Link>
              </div>

              <a
                href={maxHref}
                target="_blank"
                rel="noopener noreferrer"
                data-event="hero_consult_max"
                className="mt-3 inline-flex min-h-[34px] w-full max-w-[440px] items-center gap-2 rounded-sm bg-white px-3 text-xs text-[#656b72] transition hover:bg-white/90"
              >
                <MessageSquareText className="h-4 w-4 shrink-0 text-[#6156f5]" aria-hidden />
                <span className="font-semibold text-[#6156f5]">{h.maxPill.title}</span>
                <span className="ml-3 hidden sm:inline">{h.maxPill.note}</span>
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
