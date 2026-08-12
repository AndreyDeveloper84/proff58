import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { MapPin, Clock, Phone, Mail, Wrench, FileText, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SITE } from "@/lib/site";

// Страница «О компании» (DRF-1009).
//
// Правило этой страницы — ничего не выдумывать. Здесь нет ни «15 лет на рынке», ни
// «10 000 довольных клиентов»: такие цифры владелец не подтверждал, а непроверяемое
// число на странице о доверии работает ровно против доверия. Всё, что написано ниже,
// либо видно на фотографиях магазина, либо следует из работающего кода витрины
// (способы оплаты, счёт для организаций, состав каталога).
//
// Фотографии — реальные, сняты в магазине 10.08.2026. Стоковых и AI-картинок нет.

export const metadata: Metadata = {
  title: "О компании — магазин инструмента «Профессионал» в Пензе",
  description:
    "Магазин профессионального инструмента в Пензе: электро- и ручной инструмент, " +
    "оснастка, расходные материалы. Подбор под задачу, самовывоз и доставка, работа с организациями.",
  alternates: { canonical: "/about" },
  openGraph: {
    title: "О компании — «Профессионал»",
    description: "Магазин профессионального инструмента в Пензе: подбор под задачу, сервис, работа с организациями.",
    images: ["/about/facade.webp"],
    type: "website",
  },
};

const ASSORTMENT = [
  { label: "Электроинструмент", href: "/catalog/elektroinstrument" },
  { label: "Ручной инструмент", href: "/catalog/ruchnoy" },
  { label: "Оснастка и расходные материалы", href: "/catalog/osnastka" },
  { label: "Измерительный инструмент", href: "/catalog/izmeritelnyy" },
  { label: "Садовая техника", href: "/catalog/sadovaya" },
  { label: "Сварочное оборудование", href: "/catalog/svarka" },
];

function Section({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`mt-12 ${className}`}>
      <h2 className="font-display text-2xl font-semibold text-ink sm:text-3xl">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export default function AboutPage() {
  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 pb-16 pt-6 sm:px-6 lg:px-8">
      <nav aria-label="Хлебные крошки" className="mb-4 flex items-center gap-1 text-xs text-ink-3">
        <Link href="/" className="hover:text-accent">
          Главная
        </Link>
        <span aria-hidden>/</span>
        <span className="text-ink-2">О компании</span>
      </nav>

      {/* Первый экран. Фотографии сняты вертикально (телефон), поэтому фасад стоит
          рядом с текстом, а не растянут в баннер: кадрирование срезало бы вывеску. */}
      <div className="grid items-center gap-8 lg:grid-cols-[1fr_minmax(0,420px)]">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            О компании
          </h1>
          <p className="mt-4 text-lg text-ink-2">
            «Профессионал» — магазин инструмента в Пензе. Электро- и ручной инструмент,
            оснастка, расходные материалы, спецодежда и садовая техника: то, чем работают
            каждый день, а не то, что лежит в кладовке раз в год.
          </p>
          <p className="mt-3 text-ink-2">
            Мы продаём инструмент, помогаем подобрать его под задачу и работаем с
            организациями по счёту. Магазин и сервис — по одному адресу, на 1-м Онежском
            проезде.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href="/catalog">
              <Button variant="accent">Перейти в каталог</Button>
            </Link>
            <a href={SITE.phone.href}>
              <Button variant="outline">Позвонить {SITE.phone.display}</Button>
            </a>
          </div>
        </div>
        <Image
          src="/about/facade.webp"
          alt="Фасад магазина «Профессионал» на 1-м Онежском проезде в Пензе"
          width={788}
          height={1400}
          priority
          className="max-h-[520px] w-full rounded-lg border border-line object-cover object-center"
          sizes="(max-width: 1024px) 100vw, 420px"
        />
      </div>

      <Section title="Магазин и ассортимент">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
          <Image
            src="/about/hall.webp"
            alt="Торговый зал магазина: стеллажи с электроинструментом и садовой техникой"
            width={619}
            height={1100}
            loading="lazy"
            className="max-h-[380px] w-full rounded-lg border border-line object-cover object-center"
            sizes="(max-width: 1024px) 100vw, 320px"
          />
          <div>
            <p className="text-ink-2">
              В зале собран основной рабочий набор: дрели и шуруповёрты, шлифмашины, пилы,
              перфораторы, генераторы и мойки, ручной инструмент, крепёж и расходники.
              Витрина — не весь склад: часть позиций привозим под заказ, наличие видно в
              карточке товара на сайте.
            </p>
            <ul className="mt-4 flex flex-wrap gap-2">
              {ASSORTMENT.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="inline-flex min-h-9 items-center rounded-md border border-line bg-surface px-3 text-sm text-ink-2 transition hover:border-accent hover:text-accent"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      <Section title="Помогаем выбрать, а не просто продаём">
        <div className="grid gap-6 lg:grid-cols-[1fr_minmax(0,320px)]">
          <div>
            <p className="text-ink-2">
              Инструмент выбирают под работу: под материал, режим и то, как часто им
              пользуются. Продавец в зале разберёт задачу и покажет разницу между
              моделями — включая случаи, когда достаточно варианта попроще.
            </p>
            <p className="mt-3 text-ink-2">
              Тот же разговор возможен по телефону: если не уверены, какая оснастка
              подойдёт к вашему инструменту, позвоните — сверим по характеристикам.
            </p>
            <div className="mt-4 flex flex-wrap gap-2 text-sm text-ink-3">
              <span className="inline-flex items-center gap-1.5">
                <Wrench className="h-4 w-4" aria-hidden /> подбор под задачу
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4" aria-hidden /> проверка совместимости оснастки
              </span>
            </div>
          </div>
          <Image
            src="/about/consult.webp"
            alt="Продавец показывает покупательнице аккумуляторный шуруповёрт в торговом зале"
            width={619}
            height={1100}
            loading="lazy"
            className="max-h-[380px] w-full rounded-lg border border-line object-cover object-center"
            sizes="(max-width: 1024px) 100vw, 320px"
          />
        </div>
      </Section>

      <Section title="Организациям">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
          <Image
            src="/about/hand-tools.webp"
            alt="Витрина с ручным инструментом: ключи, головки, наборы"
            width={619}
            height={1100}
            loading="lazy"
            className="max-h-[380px] w-full rounded-lg border border-line object-cover object-center"
            sizes="(max-width: 1024px) 100vw, 320px"
          />
          <div>
            <p className="text-ink-2">
              Юридические лица и ИП оформляют заказ на сайте с оплатой по счёту:
              при оформлении выберите «Организация», укажите реквизиты — счёт придёт на
              почту и будет доступен в личном кабинете.
            </p>
            <p className="mt-3 text-ink-2">
              Для регулярных закупок удобнее завести кабинет: заказы, счета и история
              покупок хранятся в одном месте.
            </p>
            <div className="mt-4">
              <Link href="/account/login">
                <Button variant="outline">
                  <FileText className="mr-2 h-4 w-4" aria-hidden />
                  Личный кабинет
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </Section>

      <Section title="Сервис и поддержка после покупки">
        <div className="grid gap-6 lg:grid-cols-[1fr_minmax(0,320px)]">
          <div>
            <p className="text-ink-2">
              По тому же адресу работает сервис: инструмент принимают, осматривают и
              решают, что с ним делать дальше. Условия гарантийного и платного ремонта
              зависят от производителя и характера поломки — их лучше уточнить по
              телефону до того, как везти инструмент.
            </p>
            <p className="mt-3 text-ink-2">
              Отдельная страница с порядком обращения в сервис готовится.
            </p>
          </div>
          <Image
            src="/about/service.webp"
            alt="Приёмка сервиса: сотрудник оформляет документы, за ним стеллаж с запчастями"
            width={619}
            height={1100}
            loading="lazy"
            className="max-h-[380px] w-full rounded-lg border border-line object-cover object-center"
            sizes="(max-width: 1024px) 100vw, 320px"
          />
        </div>
      </Section>

      <Section title="Как нас найти">
        <div className="grid gap-4 rounded-lg border border-line bg-surface p-5 sm:grid-cols-2">
          <div className="flex items-start gap-3">
            <MapPin className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
            <div>
              <div className="text-sm text-ink-3">Адрес</div>
              <div className="text-ink">{SITE.address}</div>
              <a
                href="https://yandex.ru/maps/?text=Пенза, 1-й Онежский проезд, 12"
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-block text-sm font-medium text-accent hover:underline"
              >
                Построить маршрут
              </a>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Clock className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
            <div>
              <div className="text-sm text-ink-3">Часы работы</div>
              <div className="text-ink">{SITE.schedule}</div>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Phone className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
            <div>
              <div className="text-sm text-ink-3">Телефон</div>
              <a href={SITE.phone.href} className="text-ink hover:text-accent">
                {SITE.phone.display}
              </a>
              <div className="text-sm text-ink-3">{SITE.phoneNote}</div>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Mail className="mt-0.5 h-5 w-5 shrink-0 text-accent" aria-hidden />
            <div>
              <div className="text-sm text-ink-3">Почта</div>
              <a href={`mailto:${SITE.email}`} className="text-ink hover:text-accent">
                {SITE.email}
              </a>
            </div>
          </div>
        </div>
      </Section>
    </main>
  );
}
