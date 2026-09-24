"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { ArrowRight, Check, Plus, Trash2, X } from "lucide-react";

import { COMPARE_LIMIT, useCompare } from "@/lib/compare";
import { formatPrice, pluralize } from "@/lib/format";
import { groupProductSpecs, type SpecGroup } from "@/lib/spec-groups";
import type { ProductDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ProductImage } from "@/components/product/ProductImage";
import { AddToCartButton } from "@/components/product/AddToCartButton";
import { ProductAvailability } from "@/components/product/ProductAvailability";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";

// Строка таблицы: характеристика и её значения по каждому товару (undefined —
// характеристики у товара нет).
type Row = { label: string; values: (string | undefined)[]; differs: boolean };

// Раздел таблицы: заголовок раздела паспорта и его строки.
type RowGroup = { title: string; icon: SpecGroup["icon"]; rows: Row[] };

// Запись кэша: карточка товара либо отметка «запрашивали — сервер не отдал»
// (снят с публикации). Без отметки такой slug вечно числился бы «загружающимся».
type CacheEntry = ProductDetail | "missing";

// Раздел каталога для кнопки «Добавить товар».
type Section = { name: string; slug: string };

/**
 * Таблица сравнения.
 *
 * Выбранные товары лежат в localStorage, поэтому страница клиентская: сервер о
 * выборе не знает. Данные догружаются из same-origin BFF свежими — цены и
 * остатки в списке хранить нельзя, они меняются.
 */
export function CompareTable() {
  const { slugs, remove, clear } = useCompare();
  // Порядок выбора, без дублей и не длиннее лимита: список правится руками в
  // соседней вкладке, а BFF всё равно отдаёт не больше COMPARE_LIMIT карточек.
  const order = useMemo(() => [...new Set(slugs)].slice(0, COMPARE_LIMIT), [slugs]);

  // Кэш карточек по slug. Набор меняется по одному товару, и перезапрашивать
  // уже загруженные незачем: удаление мгновенное, добавление догружает только
  // новый товар, а остальные колонки не мигают экраном загрузки.
  const [cache, setCache] = useState<ReadonlyMap<string, CacheEntry>>(() => new Map());
  // Ключ набора, загрузка которого сорвалась. Привязка к набору, а не просто
  // флаг: стоит человеку поменять список, как старая ошибка перестаёт
  // относиться к делу и загрузка идёт заново.
  const [failedKey, setFailedKey] = useState<string | null>(null);
  // Различий у похожих товаров обычно 3-5 строк из тридцати — переключатель
  // избавляет от прокрутки одинаковых значений.
  const [onlyDiff, setOnlyDiff] = useState(false);

  // Убранный из списка товар выбрасываем из кэша: вернувшись в сравнение, он
  // загрузится заново, а не покажет цену и остаток на момент первого запроса.
  // Правка состояния прямо в рендере — штатный для React приём «состояние от
  // пропсов»: без эффекта и без лишнего кадра со старыми данными.
  const orderKey = order.join(",");
  const [cachedFor, setCachedFor] = useState(orderKey);
  if (cachedFor !== orderKey) {
    setCachedFor(orderKey);
    if ([...cache.keys()].some((slug) => !order.includes(slug))) {
      setCache((prev) => new Map([...prev].filter(([slug]) => order.includes(slug))));
    }
  }

  const pending = order.filter((slug) => !cache.has(slug));
  const pendingKey = pending.join(",");

  useEffect(() => {
    const toLoad = pendingKey ? pendingKey.split(",") : [];
    if (toLoad.length === 0 || failedKey === pendingKey) return;

    // Набор сменился, пока шёл запрос, — прежний ответ уже не нужен. Сверка
    // signal.aborted ниже страхует и от ответа, успевшего прийти до отмены:
    // поздний ответ не должен вернуть в таблицу удалённый товар.
    const controller = new AbortController();
    const query = toLoad.map(encodeURIComponent).join(",");
    fetch(`/api/catalog/compare?slugs=${query}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: { products?: ProductDetail[] }) => {
        if (controller.signal.aborted) return;
        const bySlug = new Map((data.products ?? []).map((p) => [p.slug, p]));
        setCache((prev) => {
          const next = new Map(prev);
          for (const slug of toLoad) next.set(slug, bySlug.get(slug) ?? "missing");
          return next;
        });
        setFailedKey(null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailedKey(pendingKey);
      });
    return () => controller.abort();
  }, [pendingKey, failedKey]);

  const products = order
    .map((slug) => cache.get(slug))
    .filter((entry): entry is ProductDetail => typeof entry === "object");
  const missing = order.filter((slug) => cache.get(slug) === "missing");
  const failed = pending.length > 0 && failedKey === pendingKey;
  const retry = () => setFailedKey(null);

  const emptyShell = "min-h-80 rounded-lg border border-line bg-surface shadow-sm";

  if (products.length === 0 && failed) {
    return (
      <ErrorState
        description="Не удалось загрузить товары для сравнения."
        className={emptyShell}
        action={
          <button
            type="button"
            onClick={retry}
            className="inline-flex h-11 items-center rounded-md border border-line px-4 text-sm font-medium text-ink hover:bg-raised"
          >
            Повторить
          </button>
        }
      />
    );
  }
  if (products.length === 0 && pending.length > 0) {
    return <LoadingState label="Загружаем товары…" className={emptyShell} />;
  }
  if (products.length === 0) {
    const gone = missing.length > 0;
    return (
      <EmptyState
        title={gone ? "Товары из сравнения больше не продаются" : "В сравнении пока пусто"}
        description={`Добавьте товары кнопкой сравнения в каталоге или на странице товара — до ${COMPARE_LIMIT} штук.`}
        className={emptyShell}
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Link
              href="/catalog"
              className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-accent-ink hover:brightness-95"
            >
              <Plus className="h-4 w-4" aria-hidden />
              Перейти в каталог
            </Link>
            {gone && (
              <button
                type="button"
                onClick={clear}
                className="inline-flex h-11 items-center rounded-md border border-line px-4 text-sm font-medium text-ink hover:bg-raised"
              >
                Очистить список
              </button>
            )}
          </div>
        }
      />
    );
  }

  const groups = buildGroups(products);
  const diffCount = groups.reduce((n, g) => n + g.rows.filter((r) => r.differs).length, 0);
  const visibleGroups = onlyDiff
    ? groups
        .map((g) => ({ ...g, rows: g.rows.filter((r) => r.differs) }))
        .filter((g) => g.rows.length > 0)
    : groups;
  const section = commonSection(products);
  const addLabel = section ? `Добавить товар из раздела «${section.name}»` : "Добавить товар";
  // Ширина таблицы — от числа колонок: первый столбец + минимум на товар. Узкие
  // колонки ломали бы кнопки и цены, широкие на телефоне — не нужны.
  const tableStyle = { "--compare-cols": products.length } as CSSProperties;

  return (
    <section aria-label="Параметры и таблица сравнения">
      <div className="mb-3 flex items-center justify-between gap-3 sm:hidden">
        <p className="text-xs text-ink-3">Листайте таблицу в сторону</p>
        <ArrowRight className="h-4 w-4 text-ink-3" aria-hidden />
      </div>

      <div className="overflow-hidden rounded-lg border border-line bg-surface shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-raised/60 px-3 py-3 sm:px-5">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            <p className="text-sm font-semibold text-ink">
              {products.length} {pluralize(products.length, "товар", "товара", "товаров")}
              {" "}
              <span className="font-normal text-ink-3">из {COMPARE_LIMIT}</span>
            </p>

            <label className="group inline-flex cursor-pointer items-center gap-2.5 text-sm text-ink-2">
              <span className="relative inline-flex h-6 w-10 shrink-0 items-center">
                <input
                  type="checkbox"
                  checked={onlyDiff}
                  onChange={(e) => setOnlyDiff(e.target.checked)}
                  className="peer sr-only"
                />
                <span className="absolute inset-0 rounded-full border border-line bg-surface transition-colors peer-checked:border-accent peer-checked:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-accent peer-focus-visible:ring-offset-2" />
                <span className="relative ml-1 grid h-4 w-4 place-items-center rounded-full bg-ink-3 text-transparent shadow-sm transition-all peer-checked:translate-x-4 peer-checked:bg-accent-ink peer-checked:text-accent">
                  <Check className="h-2.5 w-2.5" strokeWidth={3} aria-hidden />
                </span>
              </span>
              <span>
                Только различия
                {" "}
                <span className="text-ink-3">{diffCount}</span>
              </span>
            </label>
          </div>

          <div className="flex min-w-0 items-center gap-1 sm:gap-2">
            {order.length < COMPARE_LIMIT && (
              // Модалки подбора нет: ведём в раздел, общий для сравниваемых
              // товаров, — там лежат именно сопоставимые с ними позиции.
              <Link
                href={section ? `/catalog/${section.slug}` : "/catalog"}
                aria-label={addLabel}
                title={addLabel}
                className="inline-flex h-10 min-w-0 items-center gap-2 rounded-md px-2.5 text-sm font-medium text-brand hover:bg-surface sm:px-3"
              >
                <Plus className="h-4 w-4 shrink-0" aria-hidden />
                <span className="hidden max-w-80 truncate sm:inline">{addLabel}</span>
                <span className="sm:hidden">Добавить</span>
              </Link>
            )}
            <button
              type="button"
              onClick={clear}
              aria-label="Очистить список сравнения"
              className="inline-flex h-10 shrink-0 items-center gap-2 rounded-md px-2.5 text-sm text-ink-3 hover:bg-surface hover:text-danger sm:px-3"
            >
              <Trash2 className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">Очистить</span>
            </button>
          </div>
        </div>

        {(failed || pending.length > 0 || missing.length > 0) && (
          <div
            role="status"
            className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-3 py-2 text-xs text-ink-2 sm:px-5"
          >
            {failed ? (
              <span>
                Не удалось загрузить часть товаров.{" "}
                <button type="button" onClick={retry} className="font-medium text-brand underline">
                  Повторить
                </button>
              </span>
            ) : (
              pending.length > 0 && <span>Загружаем ещё {pending.length}…</span>
            )}
            {missing.length > 0 && (
              <span>
                {missing.length === 1
                  ? "Один товар из списка больше не продаётся."
                  : `${missing.length} ${pluralize(missing.length, "товар", "товара", "товаров")} из списка больше не продаются.`}{" "}
                <button
                  type="button"
                  onClick={() => missing.forEach(remove)}
                  className="font-medium text-brand underline"
                >
                  Убрать из списка
                </button>
              </span>
            )}
          </div>
        )}

        <p className="flex items-center gap-2 border-b border-line px-3 py-2 text-xs text-ink-3 sm:px-5">
          <span className="h-3.5 w-[3px] shrink-0 rounded-full bg-accent" aria-hidden />
          Отметка слева — значения у товаров различаются, они выделены жирным
        </p>

        {/* Прокручивается сама таблица, а не страница: горизонтальный скролл всего
            документа ломает чтение остальной витрины. Вертикальный скролл тоже
            внутри — только так строка товаров остаётся закреплённой, пока
            листаешь характеристики. overscroll-x-contain: жест вбок у края
            таблицы не уводит браузер «назад», а вертикальный упор в край
            продолжает прокрутку страницы. */}
        <div className="max-h-[max(calc(100dvh_-_8rem),20rem)] overflow-auto overscroll-x-contain">
          <table
            style={tableStyle}
            className={cn(
              // border-separate, а не collapse: при collapse границы рисует
              // таблица, и у закреплённых ячеек разделители уезжали при
              // прокрутке, скрываясь под их фоном.
              "w-full table-fixed border-separate border-spacing-0 text-sm",
              "min-w-[calc(120px_+_var(--compare-cols)_*_170px)]",
              "sm:min-w-[calc(13rem_+_var(--compare-cols)_*_240px)]",
            )}
          >
            <caption className="sr-only">Сравнение характеристик выбранных товаров</caption>
            <colgroup>
              <col className="w-[120px] sm:w-52" />
              {products.map((p) => (
                <col key={p.slug} />
              ))}
            </colgroup>
            {/* Закреплена только компактная строка «название + цена + убрать»:
                шапка целиком с фото и кнопками заняла бы полэкрана телефона.
                sticky стоит на ячейках, а не на thead/tr — Safari не
                закрепляет части таблицы. */}
            <thead>
              <tr>
                <td className="sticky left-0 z-10 border-r border-line bg-surface p-3 align-top sm:px-5 sm:pt-5">
                  <span className="hidden text-xs leading-5 text-ink-3 sm:block">
                    Цена и наличие актуальны на сейчас
                  </span>
                </td>
                {products.map((p) => (
                  <td key={p.slug} className="border-r border-line p-3 align-top sm:px-5 sm:pt-5">
                    <Link href={`/product/${p.slug}`} tabIndex={-1} className="block w-24 sm:w-28">
                      <ProductImage
                        src={p.images[0]?.url}
                        alt={p.name}
                        sizes="112px"
                        normalized={p.images[0]?.normalized}
                        className="ring-1 ring-line"
                      />
                    </Link>
                    {p.brand && (
                      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
                        {p.brand}
                      </p>
                    )}
                  </td>
                ))}
              </tr>
              <tr>
                <td className="sticky left-0 top-0 z-30 border-b border-r border-line bg-surface px-3 py-2 align-middle sm:px-5">
                  <span className="font-display text-base font-semibold text-ink">Товары</span>
                </td>
                {products.map((p) => (
                  <th
                    key={p.slug}
                    scope="col"
                    className="sticky top-0 z-20 border-b border-r border-line bg-surface px-3 py-2 text-left align-top font-normal sm:px-5"
                  >
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <Link
                          href={`/product/${p.slug}`}
                          title={p.name}
                          className="line-clamp-2 text-[13px] font-semibold leading-[18px] text-ink hover:text-accent sm:text-sm sm:leading-5"
                        >
                          {p.name}
                        </Link>
                        <p className="mt-0.5 font-display text-sm font-bold leading-5 text-ink sm:text-base sm:leading-6">
                          {p.price.final != null ? formatPrice(p.price.final) : "Цена уточняется"}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => remove(p.slug)}
                        aria-label={`Убрать ${p.name} из сравнения`}
                        className="-mr-1 grid h-9 w-9 shrink-0 place-items-center rounded-full text-ink-3 ring-1 ring-line transition-colors hover:text-danger"
                      >
                        <X className="h-4 w-4" aria-hidden />
                      </button>
                    </div>
                  </th>
                ))}
              </tr>
              <tr>
                <td className="sticky left-0 z-10 border-b border-r border-line bg-surface px-3 py-3 sm:px-5" />
                {products.map((p) => (
                  <td key={p.slug} className="border-b border-r border-line px-3 py-3 align-top sm:px-5">
                    <ProductAvailability stock={p.stock} stockQty={p.stockQty} />
                    <div className="mt-2 max-w-48">
                      <AddToCartButton
                        productId={p.id}
                        productSlug={p.slug}
                        stock={p.stock}
                        hasPrice={p.price.final != null}
                        fullWidth
                        showLabel
                      />
                    </div>
                  </td>
                ))}
              </tr>
            </thead>
            {visibleGroups.map((group) => {
              const Icon = group.icon;
              return (
                <tbody key={group.title}>
                  <tr>
                    {/* Заголовок раздела — на всю строку: в узком первом столбце
                        «Производительность» рвалась посреди слова. Липкая сама
                        подпись внутри ячейки — при горизонтальной прокрутке она
                        остаётся у левого края, как названия характеристик. */}
                    <th
                      scope="rowgroup"
                      colSpan={products.length + 1}
                      className="border-b border-line bg-raised p-0 text-left"
                    >
                      <span className="sticky left-0 flex w-max items-center gap-2 px-3 py-2.5 font-semibold text-ink sm:px-5">
                        <Icon className="h-4 w-4 shrink-0 text-accent" aria-hidden />
                        {group.title}
                      </span>
                    </th>
                  </tr>
                  {group.rows.map((row) => (
                    <tr key={row.label} className="group">
                      <th
                        scope="row"
                        className={cn(
                          "sticky left-0 z-10 break-words border-b border-r border-line bg-surface px-3 py-3 text-left font-normal leading-5 group-hover:bg-raised sm:px-5",
                          // Различие — тонкая полоса у названия: inset-тень не
                          // сдвигает текст и не меняет ширину колонки.
                          row.differs
                            ? "text-ink shadow-[inset_3px_0_0_var(--color-accent)]"
                            : "text-ink-3",
                        )}
                      >
                        {row.label}
                        {row.differs && <span className="sr-only"> (значения различаются)</span>}
                      </th>
                      {row.values.map((value, i) => (
                        <td
                          key={`${row.label}-${i}`}
                          className={cn(
                            "break-words border-b border-r border-line px-3 py-3 leading-5 group-hover:bg-raised sm:px-5",
                            row.differs ? "font-semibold text-ink" : "text-ink-2",
                          )}
                        >
                          {/* Прочерк вместо пустоты: «характеристика не заполнена» —
                              это тоже результат сравнения, и он должен читаться. */}
                          {value ?? "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              );
            })}
          </table>

          {visibleGroups.length === 0 && (
            <p className="border-t border-line bg-raised/50 p-6 text-center text-sm text-ink-2">
              {onlyDiff
                ? "По заполненным характеристикам товары одинаковы."
                : "У выбранных товаров не заполнены характеристики."}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

/**
 * Собрать строки таблицы: объединение характеристик всех товаров.
 *
 * Порядок — как у первого товара, чтобы таблица не перетасовывалась при
 * удалении колонок; характеристики, которых у него нет, добавляются следом.
 * Строка, не заполненная ни у одного товара, не нужна: в ней одни прочерки.
 * Строка помечается различающейся, если среди ЗАПОЛНЕННЫХ значений есть разные
 * либо характеристика заполнена не у всех.
 */
export function buildRows(products: ProductDetail[]): Row[] {
  const labels: string[] = [];
  for (const product of products) {
    for (const spec of product.specs) {
      if (!labels.includes(spec.label)) labels.push(spec.label);
    }
  }

  return labels
    .map((label) => {
      const values = products.map(
        (p) => p.specs.find((s) => s.label === label)?.value.trim() || undefined,
      );
      const filled = values.filter((v): v is string => v !== undefined);
      const differs = filled.length !== values.length || new Set(filled).size > 1;
      return { label, values, differs };
    })
    .filter((row) => row.values.some((v) => v !== undefined));
}

/**
 * Разложить строки по разделам технического паспорта — тем же, что на странице
 * товара. Раздел без строк не попадает в таблицу.
 */
export function buildGroups(products: ProductDetail[]): RowGroup[] {
  const rows = buildRows(products);
  const byLabel = new Map(rows.map((row) => [row.label, row]));
  return groupProductSpecs(rows.map((row) => ({ label: row.label, value: "" }))).map(
    (group) => ({
      title: group.title,
      icon: group.icon,
      rows: group.specs.map((spec) => byLabel.get(spec.label)!),
    }),
  );
}

/**
 * Самый глубокий раздел каталога, общий для всех товаров (общий префикс
 * хлебных крошек). null — товары из разных верхних разделов.
 *
 * Фильтр по типу инструмента (?tool_type=) сюда не добавляется: detail-ответ
 * отдаёт тип подписью опции, а каталогу нужен её slug.
 */
export function commonSection(products: ProductDetail[]): Section | null {
  if (products.length === 0) return null;
  let prefix = products[0].breadcrumb;
  for (const product of products.slice(1)) {
    let i = 0;
    while (
      i < prefix.length &&
      i < product.breadcrumb.length &&
      prefix[i].slug === product.breadcrumb[i].slug
    ) {
      i += 1;
    }
    prefix = prefix.slice(0, i);
  }
  return prefix.at(-1) ?? null;
}
