"use client";

import Image from "next/image";
import Link from "next/link";
import {
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
            // На узком экране текст занимает всю ширину и ложится прямо на
            // фотографию — горизонтальный градиент к правому краю прозрачен, и
            // строки терялись на бликах металла. До sm затемняем сверху вниз,
            // дальше остаётся исходная раскладка «текст слева, инструмент справа».
            className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(5,8,10,.95)_0%,rgba(5,8,10,.88)_55%,rgba(5,8,10,.78)_100%)] sm:bg-[linear-gradient(90deg,rgba(5,8,10,.98)_0%,rgba(5,8,10,.91)_31%,rgba(5,8,10,.54)_51%,rgba(5,8,10,.08)_74%)]"
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

              {/* Кнопки и MAX-пилюля — один блок одной ширины. На десктопе ширину
                  блока задаёт самый широкий элемент (пилюля с подсказкой), а кнопки
                  делят её поровну через flex-1 — иначе пилюля торчала бы правее
                  кнопок. На мобильной блок занимает всю ширину колонки: кнопки идут
                  столбиком, пилюля выравнивается по ним. */}
              <div className="mt-4 sm:w-fit">
                <div className="flex flex-col gap-3 sm:flex-row">
                  <button
                    type="button"
                    onClick={onConsult}
                    className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-sm bg-accent px-7 text-[13px] font-semibold text-accent-ink transition hover:brightness-110 sm:flex-1"
                  >
                    {h.primaryCta.label}
                  </button>
                  <Link
                    href={h.secondaryCta.href}
                    className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-sm border border-white/80 bg-white px-8 text-[13px] font-semibold text-[#202326] transition hover:bg-white/90 sm:flex-1"
                  >
                    {h.secondaryCta.label}
                  </Link>
                </div>

                <a
                  href={maxHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-event="hero_consult_max"
                  className="mt-3 flex min-h-[34px] w-full items-center gap-2.5 rounded-sm bg-white px-3.5 text-xs text-[#656b72] transition hover:bg-white/90"
                >
                  {/* Фирменное лого MAX из ассетов проекта — по правке ревью. */}
                  <Image
                    src="/brands/max-colored.png"
                    alt=""
                    width={20}
                    height={20}
                    className="h-[18px] w-[18px] shrink-0 object-contain"
                    aria-hidden
                  />
                  <span className="whitespace-nowrap font-semibold text-[#6156f5]">
                    {h.maxPill.title}
                  </span>
                  <span className="ml-2 hidden whitespace-nowrap sm:inline">{h.maxPill.note}</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
