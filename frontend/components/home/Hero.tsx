"use client";

import Image from "next/image";
import { useState } from "react";
import {
  ShieldCheck,
  Truck,
  Users,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HOME_CONTENT } from "@/lib/home-content";

const BULLET_ICONS: Record<string, LucideIcon> = {
  ShieldCheck,
  Truck,
  Users,
  Wrench,
};

// Первый экран по утверждённому макету. Текст остаётся HTML, а сгенерированная
// фотография используется только как декоративный фон.
//
// Кнопок здесь нет: «Подобрать инструмент» и «Перейти в каталог» убраны по
// решению команды. Переход в каталог остаётся зелёной кнопкой в шапке — она
// видна на каждой странице, а не только на первом экране.
export function Hero() {
  const h = HOME_CONTENT.hero;
  const [imageLoaded, setImageLoaded] = useState(false);
  return (
    <section className="bg-surface">
      <div className="mx-auto w-full max-w-[1680px] px-4 pt-2 sm:px-6 xl:px-8">
        <div className="dark relative min-h-[300px] overflow-hidden rounded-md bg-header xl:min-h-[340px]">
          <Image
            src="/home/hero/approved-tools-hero.webp"
            alt=""
            width={1881}
            height={836}
            priority
            sizes="(max-width: 768px) 700px, 1100px"
            onLoad={() => setImageLoaded(true)}
            className={`absolute right-0 top-1/2 h-full w-auto max-w-none -translate-y-1/2 object-contain transition-opacity duration-300 sm:h-[155%] xl:h-[180%] ${
              imageLoaded ? "opacity-95" : "opacity-0"
            }`}
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
          <div className="relative flex min-h-[300px] items-center px-5 py-6 sm:px-8 lg:px-12 lg:py-6 xl:min-h-[340px] xl:px-14">
            <div className="w-full max-w-[680px]">
              <h1 className="font-sans text-[29px] font-extrabold leading-[1.08] tracking-[-0.02em] text-white sm:text-[31px] xl:text-[35px]">
                {h.titleLine1}
              </h1>
              <p className="mt-1 font-sans text-[22px] font-bold leading-tight text-white sm:text-[24px] xl:text-[27px]">
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
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
