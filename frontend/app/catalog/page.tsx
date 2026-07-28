import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Boxes,
  PackageOpen,
} from "lucide-react";
import { WhyBuyStrip } from "@/components/home/HomeBottom";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { SearchBar } from "@/components/layout/SearchBar";
import { getCategoryTreeOrNull, type CategoryNode } from "@/lib/catalog";
import { SITE } from "@/lib/site";

// Категории берём из API в рантайме (slug'и из БД), без редиректа. Данные — через
// lib/catalog.ts (единственная точка интеграции), fetch тут не дублируем.
export const dynamic = "force-dynamic";

// В API пока нет category.image. Иллюстрация — только оформление реального узла;
// она определяется по имени, но название, ссылка и подкатегории всегда серверные.
// Для нового неизвестного раздела есть нейтральный fallback, поэтому расширение
// дерева на backend не требует срочной правки frontend.
//
// Чертежи-скелетоны 1200×520 рисовались под этот блок: широкий кадр, объекты
// по центру, размерные выноски акцентным цветом. Перфораторы стоят выше общего
// правила «электроинструмент» — у них свой чертёж.
function categoryArtwork(name: string): string | null {
  const value = name.toLocaleLowerCase("ru-RU");
  const rules: Array<[RegExp, string]> = [
    [/перфоратор/, "/catalog/skeletons/perforatory.png"],
    [/оснаст|расход/, "/catalog/skeletons/osnastka.png"],
    [/электроинструмент/, "/catalog/skeletons/electroinstrument.png"],
    [/ручн/, "/catalog/skeletons/ruchnoy.png"],
    [/авто|гараж/, "/catalog/skeletons/avto-garage.png"],
    [/измер/, "/catalog/skeletons/izmeritelnyy.png"],
    [/крепёж|метиз/, "/catalog/skeletons/krepezh.png"],
    [/электрик|освещ/, "/catalog/skeletons/electrika.png"],
    [/спецодеж|сиз/, "/catalog/skeletons/siz.png"],
    [/садов/, "/catalog/skeletons/sadovaya.png"],
    [/силов|пневм|компресс/, "/catalog/skeletons/silovaya.png"],
    [/свароч/, "/catalog/skeletons/svarochnaya.png"],
    [/хранен|организац/, "/catalog/skeletons/hranenie.png"],
    [/строитель|отделоч/, "/catalog/skeletons/stroitelnyy.png"],
    [/запчаст|аккумулятор|комплектующ/, "/catalog/skeletons/zapchasti.png"],
  ];

  return rules.find(([pattern]) => pattern.test(value))?.[1] ?? null;
}

// Все карточки одного размера: чертёж в кадре 1200×520 сверху, под ним название
// и состав раздела. Контраст линий поднят в самих файлах (гамма-коррекция при
// подготовке ассетов) — рантайм-фильтр на полтора десятка растров стоил бы
// заметной отрисовки на слабых машинах.
function CategoryCard({ category }: { category: CategoryNode }) {
  const artwork = categoryArtwork(category.name);
  const children = category.children.slice(0, 3);

  return (
    <Link
      href={`/catalog/${category.slug}`}
      className="group flex flex-col overflow-hidden rounded-md border border-line bg-surface transition duration-200 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-md"
    >
      <span className="relative block aspect-[1200/520] w-full overflow-hidden bg-raised/40">
        {artwork ? (
          <Image
            src={artwork}
            alt=""
            fill
            loading="eager"
            unoptimized
            sizes="(max-width: 639px) 46vw, (max-width: 1023px) 30vw, 330px"
            className="object-contain p-1.5 transition duration-300 group-hover:scale-[1.04]"
            aria-hidden
          />
        ) : (
          <span className="grid h-full place-items-center text-accent" aria-hidden>
            <Boxes className="h-9 w-9" strokeWidth={1.4} />
          </span>
        )}
      </span>

      <span className="flex flex-1 flex-col border-t border-line px-3 py-2.5">
        <span className="flex items-start gap-2">
          <h2 className="line-clamp-2 min-w-0 flex-1 text-[12px] font-semibold leading-[1.3] text-ink transition group-hover:text-accent lg:text-[13px]">
            {category.name}
          </h2>
          <ArrowRight
            className="mt-0.5 h-4 w-4 shrink-0 text-accent transition-transform group-hover:translate-x-0.5"
            aria-hidden
          />
        </span>

        {children.length > 0 && (
          <span className="mt-1 line-clamp-2 text-[10px] leading-[1.35] text-ink-3">
            {children.map((child) => child.name).join(", ")}
          </span>
        )}
      </span>
    </Link>
  );
}

function CatalogConsultBanner() {
  return (
    <section className="mt-3 flex min-h-14 items-center gap-3 rounded-md border border-line bg-surface px-3 py-2 lg:px-4">
      <Image
        src="/brands/max-colored.png"
        alt=""
        width={32}
        height={32}
        className="h-8 w-8 shrink-0 object-contain"
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-[#6156f5]">Консультация в MAX</p>
        <p className="truncate text-[11px] text-ink-2">
          Подберём инструмент под вашу задачу и бюджет
        </p>
      </div>
      <span className="hidden text-[11px] text-ink-3 lg:block">
        Ответим в чате за 2–3 минуты
      </span>
      <a
        href={SITE.support.max.href}
        target="_blank"
        rel="noopener noreferrer"
        data-event="catalog_max_click"
        className="inline-flex h-9 shrink-0 items-center justify-center rounded-sm bg-[#6156f5] px-5 text-xs font-semibold text-white transition hover:bg-[#5147dc]"
      >
        Написать
      </a>
    </section>
  );
}

// Суффикс «— Профессионал» дописывает шаблон title из app/layout.tsx.
export async function generateMetadata() {
  return { title: "Каталог" };
}

export default async function CatalogIndexPage() {
  const categories = await getCategoryTreeOrNull();

  return (
    <main className="min-h-[70vh] bg-surface pb-20 lg:pb-0">
      <div className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6 lg:px-4 lg:py-5">
        <nav
          aria-label="Хлебные крошки"
          className="mb-3 flex items-center gap-2 text-xs text-ink-3"
        >
          <Link href="/" className="transition hover:text-accent">
            Главная
          </Link>
          <span aria-hidden>›</span>
          <span className="text-ink-2">Каталог</span>
        </nav>

        <h1 className="font-display text-[28px] font-semibold text-ink lg:text-[32px]">
          Каталог товаров
        </h1>

        <SearchBar
          className="mt-3 max-w-none [&_input]:h-10 lg:mt-3"
          placeholder="Поиск по каталогу"
        />

        {categories == null ? (
          <section className="mt-5 grid min-h-64 place-items-center rounded-lg border border-line bg-surface p-8 text-center">
            <div>
              <PackageOpen className="mx-auto h-12 w-12 text-ink-3" aria-hidden />
              <h2 className="mt-4 text-lg font-semibold text-ink">
                Каталог временно недоступен
              </h2>
              <p className="mt-1 text-sm text-ink-2">Обновите страницу немного позже.</p>
            </div>
          </section>
        ) : categories.length === 0 ? (
          <section className="mt-5 grid min-h-64 place-items-center rounded-lg border border-line bg-surface p-8 text-center">
            <div>
              <PackageOpen className="mx-auto h-12 w-12 text-ink-3" aria-hidden />
              <h2 className="mt-4 text-lg font-semibold text-ink">Категории пока не заполнены</h2>
              <p className="mt-1 text-sm text-ink-2">
                После публикации разделов они появятся здесь автоматически.
              </p>
            </div>
          </section>
        ) : (
          <>
            {/* На узком экране — одна колонка: в кадре шириной в пол-экрана чертёж
                нечитаем, а названия рвутся посреди слова. */}
            <section
              aria-label="Категории товаров"
              className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4 lg:gap-2.5"
            >
              {categories.map((category) => (
                <CategoryCard key={category.id} category={category} />
              ))}
            </section>

            <CatalogConsultBanner />
            <div className="mt-3 hidden lg:block">
              <WhyBuyStrip />
            </div>
          </>
        )}
      </div>

      <MobileBottomNav active="catalog" />
    </main>
  );
}
