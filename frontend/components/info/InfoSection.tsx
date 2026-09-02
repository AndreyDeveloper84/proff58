import Image from "next/image";
import Link from "next/link";
import { Check, Clock, Mail, MapPin, Phone, TriangleAlert } from "lucide-react";

import { InfoBlocks } from "@/components/info/InfoBlocks";
import { YandexMap } from "@/components/info/YandexMap";
import { buttonVariants } from "@/components/ui/button";
import type { InfoSection as Section } from "@/lib/info-pages";
import { cn } from "@/lib/utils";

// Секции инфо-страницы. Структура блоков живёт здесь, в коде, а их наполнение —
// в админке: макет задаёт, как выглядит «сетка карточек», а что в этих карточках
// написано, решает владелец, не трогая релиз.
//
// Тип секции приходит с сервера строкой (`layout`), уже разобранной из разметки.
// Неизвестный тип — не ошибка: секция отрисуется как обычный текст. Так страница
// переживает и старый контент, написанный сплошными абзацами, и новый тип блока,
// который завели в разметке раньше, чем в вёрстке.

const WARNING_TONE = "предупреждение";

function Buttons({ buttons }: { buttons: Section["buttons"] }) {
  if (buttons.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-3">
      {buttons.map((button) => (
        <Link
          key={`${button.label}-${button.href}`}
          href={button.href || "#"}
          className={buttonVariants({
            variant: button.style === "outline" ? "outline" : "accent",
            size: "lg",
          })}
        >
          {button.label}
        </Link>
      ))}
    </div>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-display text-xl font-semibold tracking-tight text-ink sm:text-2xl">
      {children}
    </h2>
  );
}

function Hero({ section }: { section: Section }) {
  const images = section.meta.images ?? (section.meta.image ? [section.meta.image] : []);
  return (
    // Без картинки колонка не нужна: пустая половина экрана рядом с заголовком
    // читается как незагрузившийся блок, а не как воздух.
    <section className={cn("grid items-center gap-8", images.length > 0 && "lg:grid-cols-2")}>
      <div className="space-y-5">
        {section.meta.badge ? (
          <p className="text-xs font-semibold uppercase tracking-widest text-accent">
            {section.meta.badge}
          </p>
        ) : null}
        <h1 className="font-display text-3xl font-bold uppercase leading-tight tracking-tight text-ink sm:text-4xl">
          {section.heading}
        </h1>
        <InfoBlocks blocks={section.blocks} />
        <Buttons buttons={section.buttons} />
      </div>
      {images.length > 0 ? (
        // Коллаж из трёх фото на широком экране и одно ведущее на телефоне:
        // три картинки в колонку — это три экрана прокрутки до первого текста.
        <div
          className={cn(
            "grid gap-3",
            images.length > 1 ? "grid-cols-2 [&>*:first-child]:col-span-2" : "grid-cols-1",
          )}
        >
          {images.map((src, index) => (
            <div
              key={src}
              className={cn(
                "relative overflow-hidden rounded-xl border border-line bg-raised",
                index === 0 ? "aspect-[16/10]" : "aspect-[4/3]",
                index > 0 && "hidden sm:block",
              )}
            >
              <Image
                src={src}
                alt=""
                fill
                sizes="(min-width: 1024px) 45vw, 100vw"
                className="object-cover"
                priority={index === 0}
              />
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function Cards({ section }: { section: Section }) {
  return (
    <section className="space-y-6">
      {section.heading ? <Heading>{section.heading}</Heading> : null}
      <InfoBlocks blocks={section.blocks} />
      {/* Колонок ровно столько, сколько карточек, пока их не больше четырёх:
          иначе последняя висит одна в ряду и выглядит потерянной. */}
      <div
        className={cn(
          "grid gap-4 sm:grid-cols-2",
          section.items.length === 4 ? "lg:grid-cols-4" : "lg:grid-cols-3",
        )}
      >
        {section.items.map((item) => (
          <article
            key={item.title}
            className="rounded-xl border border-line bg-surface p-5 transition-colors hover:border-accent/40"
          >
            <h3 className="text-base font-semibold text-ink">{item.title}</h3>
            {item.text ? (
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{item.text}</p>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function Steps({ section }: { section: Section }) {
  return (
    <section className="space-y-6">
      {section.heading ? <Heading>{section.heading}</Heading> : null}
      <InfoBlocks blocks={section.blocks} />
      <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {section.items.map((item, index) => (
          <li key={item.title} className="rounded-xl border border-line bg-surface p-5">
            <span className="font-display text-2xl font-bold text-accent">
              {String(index + 1).padStart(2, "0")}
            </span>
            <h3 className="mt-2 text-base font-semibold text-ink">{item.title}</h3>
            {item.text ? (
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{item.text}</p>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Checklist({ section }: { section: Section }) {
  const warning = section.meta.tone === WARNING_TONE;
  const Icon = warning ? TriangleAlert : Check;
  return (
    <section
      className={cn(
        "rounded-xl border p-6",
        warning ? "border-rating/40 bg-rating/5" : "border-line bg-surface",
      )}
    >
      {section.heading ? <Heading>{section.heading}</Heading> : null}
      <div className="mt-4 space-y-4">
        <InfoBlocks blocks={section.blocks} />
        <ul className="space-y-3">
          {section.items.map((item) => (
            <li key={item.title} className="flex gap-3 text-sm leading-relaxed text-ink-2">
              <Icon
                aria-hidden
                className={cn("mt-0.5 size-4 shrink-0", warning ? "text-rating" : "text-accent")}
              />
              <span>
                <span className="text-ink">{item.title}</span>
                {item.text ? ` — ${item.text}` : null}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Faq({ section }: { section: Section }) {
  // Вопросы без ответа не показываем: пустой аккордеон выглядит поломкой, а
  // ответы владелец дописывает в админке по одному.
  const answered = section.items.filter((item) => item.text);
  if (answered.length === 0) return null;
  return (
    <section className="space-y-4">
      {section.heading ? <Heading>{section.heading}</Heading> : null}
      <div className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {answered.map((item, index) => (
          // <details> вместо состояния в React: аккордеон работает без JS,
          // открывается по ссылке-якорю и доступен с клавиатуры «из коробки».
          <details key={item.title} className="group" open={index === 0}>
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-left text-base font-medium text-ink">
              {item.title}
              <span
                aria-hidden
                className="text-ink-3 transition-transform group-open:rotate-45"
              >
                +
              </span>
            </summary>
            <p className="px-5 pb-4 text-sm leading-relaxed text-ink-2">{item.text}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

function Chips({ section }: { section: Section }) {
  return (
    <section className="grid items-center gap-8 lg:grid-cols-2">
      <div className="space-y-5">
        {section.heading ? <Heading>{section.heading}</Heading> : null}
        <InfoBlocks blocks={section.blocks} />
        {section.items.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {section.items.map((item) => (
              <li
                key={item.title}
                className="rounded-full border border-line bg-raised px-3 py-1.5 text-sm text-ink-2"
              >
                {item.title}
              </li>
            ))}
          </ul>
        ) : null}
        <Buttons buttons={section.buttons} />
      </div>
      {section.meta.image ? (
        <div className="relative aspect-[4/3] overflow-hidden rounded-xl border border-line bg-raised">
          <Image
            src={section.meta.image}
            alt=""
            fill
            sizes="(min-width: 1024px) 45vw, 100vw"
            className="object-cover"
          />
        </div>
      ) : null}
    </section>
  );
}

function ContactLines({ section }: { section: Section }) {
  const { phone, email, hours, address } = section.meta;
  return (
    <ul className="space-y-2 text-sm text-ink-2">
      {address ? (
        <li className="flex items-center gap-2">
          <MapPin aria-hidden className="size-4 text-accent" />
          {address}
        </li>
      ) : null}
      {phone ? (
        <li className="flex items-center gap-2">
          <Phone aria-hidden className="size-4 text-accent" />
          <a href={`tel:${phone.replace(/[^\d+]/g, "")}`} className="hover:text-accent">
            {phone}
          </a>
        </li>
      ) : null}
      {email ? (
        <li className="flex items-center gap-2">
          <Mail aria-hidden className="size-4 text-accent" />
          <a href={`mailto:${email}`} className="hover:text-accent">
            {email}
          </a>
        </li>
      ) : null}
      {hours ? (
        <li className="flex items-center gap-2">
          <Clock aria-hidden className="size-4 text-accent" />
          {hours}
        </li>
      ) : null}
    </ul>
  );
}

function Contacts({ section }: { section: Section }) {
  return (
    <section className="grid items-center gap-8 rounded-xl border border-line bg-surface p-6 lg:grid-cols-2">
      {section.meta.image ? (
        <div className="relative aspect-[16/10] overflow-hidden rounded-lg border border-line bg-raised">
          <Image
            src={section.meta.image}
            alt=""
            fill
            sizes="(min-width: 1024px) 45vw, 100vw"
            className="object-cover"
          />
        </div>
      ) : null}
      <div className="space-y-5">
        {section.heading ? <Heading>{section.heading}</Heading> : null}
        <InfoBlocks blocks={section.blocks} />
        <ContactLines section={section} />
        <Buttons buttons={section.buttons} />
      </div>
    </section>
  );
}

function MapSection({ section }: { section: Section }) {
  return (
    <section className="grid items-stretch gap-6 lg:grid-cols-2">
      <div className="space-y-5 rounded-xl border border-line bg-surface p-6">
        {section.heading ? <Heading>{section.heading}</Heading> : null}
        {section.meta.address ? (
          <p className="font-display text-lg font-semibold uppercase text-ink">
            {section.meta.address}
          </p>
        ) : null}
        <InfoBlocks blocks={section.blocks} />
        <ContactLines section={{ ...section, meta: { ...section.meta, address: undefined } }} />
        <Buttons buttons={section.buttons} />
      </div>
      <YandexMap address={section.meta.address} className="h-full min-h-64" />
    </section>
  );
}

function Plain({ section }: { section: Section }) {
  return (
    <section className="space-y-4">
      {section.heading ? <Heading>{section.heading}</Heading> : null}
      <InfoBlocks blocks={section.blocks} />
      {section.items.length > 0 ? (
        <ul className="space-y-2 text-base text-ink-2">
          {section.items.map((item) => (
            <li key={item.title}>
              <span className="text-ink">{item.title}</span>
              {item.text ? ` — ${item.text}` : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function InfoSection({ section }: { section: Section }) {
  switch (section.layout) {
    case "hero":
      return <Hero section={section} />;
    case "cards":
      return <Cards section={section} />;
    case "steps":
      return <Steps section={section} />;
    case "checklist":
      return <Checklist section={section} />;
    case "faq":
      return <Faq section={section} />;
    case "chips":
      return <Chips section={section} />;
    case "contacts":
      return <Contacts section={section} />;
    case "map":
      return <MapSection section={section} />;
    default:
      return <Plain section={section} />;
  }
}
