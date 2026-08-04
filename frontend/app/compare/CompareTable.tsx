"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Check, Plus, SlidersHorizontal, Trash2, X } from "lucide-react";

import { COMPARE_LIMIT, useCompare } from "@/lib/compare";
import { formatPrice, pluralize } from "@/lib/format";
import type { ProductDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ProductImage } from "@/components/product/ProductImage";
import { AddToCartButton } from "@/components/product/AddToCartButton";
import { ProductAvailability } from "@/components/product/ProductAvailability";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";

// Строка таблицы: характеристика и её значения по каждому товару (undefined —
// характеристики у товара нет).
type Row = { label: string; values: (string | undefined)[]; differs: boolean };

/**
 * Таблица сравнения.
 *
 * Выбранные товары лежат в localStorage, поэтому страница клиентская: сервер о
 * выборе не знает. Данные догружаются из same-origin BFF свежими — цены и
 * остатки в списке хранить нельзя, они меняются.
 */
export function CompareTable() {
  const { slugs, remove, clear } = useCompare();
  const [products, setProducts] = useState<ProductDetail[] | null>(null);
  const [failed, setFailed] = useState(false);
  // Различий у похожих товаров обычно 3-5 строк из тридцати — переключатель
  // избавляет от прокрутки одинаковых значений.
  const [onlyDiff, setOnlyDiff] = useState(false);

  // Пустой список разбирается в рендере (ниже), а не через setState в эффекте:
  // лишний прогон рендера ради заведомо известного результата не нужен.
  useEffect(() => {
    if (slugs.length === 0) return;
    let active = true;
    fetch(`/api/catalog/compare?slugs=${slugs.map(encodeURIComponent).join(",")}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data) => {
        if (!active) return;
        setFailed(false);
        // Порядок ответа не гарантирован — выстраиваем по порядку выбора.
        const bySlug = new Map<string, ProductDetail>(
          (data.products as ProductDetail[]).map((p) => [p.slug, p]),
        );
        setProducts(slugs.map((s) => bySlug.get(s)).filter((p): p is ProductDetail => Boolean(p)));
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [slugs]);

  if (failed) {
    return (
      <ErrorState
        description="Не удалось загрузить товары для сравнения."
        className="min-h-80 rounded-lg border border-line bg-surface shadow-sm"
      />
    );
  }
  if (slugs.length > 0 && products === null) {
    return (
      <LoadingState
        label="Загружаем товары…"
        className="min-h-80 rounded-lg border border-line bg-surface shadow-sm"
      />
    );
  }
  if (slugs.length === 0 || products === null || products.length === 0) {
    return (
      <EmptyState
        title="В сравнении пока пусто"
        description={`Добавьте товары кнопкой сравнения в каталоге или на странице товара — до ${COMPARE_LIMIT} штук.`}
        className="min-h-80 rounded-lg border border-line bg-surface shadow-sm"
        action={
          <Link
            href="/catalog"
            className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-accent-ink hover:brightness-95"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Перейти в каталог
          </Link>
        }
      />
    );
  }

  const rows = buildRows(products);
  const visibleRows = onlyDiff ? rows.filter((r) => r.differs) : rows;
  const diffCount = rows.filter((r) => r.differs).length;
  const tableWidth =
    products.length === 1
      ? "min-w-[520px]"
      : products.length === 2
        ? "min-w-[760px]"
        : products.length === 3
          ? "min-w-[1000px]"
          : "min-w-[1240px]";

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

          <div className="flex items-center gap-1 sm:gap-2">
            {products.length < COMPARE_LIMIT && (
              <Link
                href="/catalog"
                className="inline-flex h-10 items-center gap-2 rounded-md px-2.5 text-sm font-medium text-brand hover:bg-surface sm:px-3"
              >
                <Plus className="h-4 w-4" aria-hidden />
                <span className="hidden sm:inline">Добавить товар</span>
                <span className="sm:hidden">Добавить</span>
              </Link>
            )}
            <button
              type="button"
              onClick={clear}
              aria-label="Очистить список сравнения"
              className="inline-flex h-10 items-center gap-2 rounded-md px-2.5 text-sm text-ink-3 hover:bg-surface hover:text-danger sm:px-3"
            >
              <Trash2 className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">Очистить</span>
            </button>
          </div>
        </div>

        {/* Прокручивается сама таблица, а не страница: горизонтальный скролл всего
            документа ломает чтение остальной витрины. */}
        <div className="overflow-x-auto overscroll-x-contain">
          <table className={cn(
              // border-separate, а не collapse: при collapse границы рисует
              // таблица, и у закреплённого столбца разделители уезжали при
              // прокрутке, скрываясь под его фоном.
              "w-full table-fixed border-separate border-spacing-0 text-sm",
              tableWidth,
            )}>
            <caption className="sr-only">Сравнение характеристик выбранных товаров</caption>
            <colgroup>
              <col className="w-32 sm:w-52" />
              {products.map((p) => (
                <col key={p.slug} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th
                  scope="row"
                  className="sticky left-0 z-20 border-b border-r border-line bg-surface p-3 text-left align-top sm:p-5"
                >
                  <span className="font-display text-base font-semibold text-ink sm:text-lg">
                    Товары
                  </span>
                  <span className="mt-1 hidden text-xs font-normal leading-5 text-ink-3 sm:block">
                    Цена и наличие актуальны на сейчас
                  </span>
                </th>
                {products.map((p) => (
                  <th
                    key={p.slug}
                    scope="col"
                    className="border-b border-r border-line p-3 text-left align-top font-normal sm:p-5"
                  >
                    <article className="relative lg:grid lg:grid-cols-[112px_minmax(0,1fr)] lg:gap-4">
                      <button
                        type="button"
                        onClick={() => remove(p.slug)}
                        aria-label={`Убрать ${p.name} из сравнения`}
                        className="absolute -right-1 -top-1 z-10 grid h-9 w-9 place-items-center rounded-full bg-surface text-ink-3 shadow-sm ring-1 ring-line transition-colors hover:text-danger"
                      >
                        <X className="h-4 w-4" aria-hidden />
                      </button>
                      <Link
                        href={`/product/${p.slug}`}
                        className="block w-24 sm:w-28 lg:w-full"
                      >
                        <ProductImage
                          src={p.images[0]?.url}
                          alt={p.name}
                          sizes="112px"
                          className="ring-1 ring-line"
                        />
                      </Link>
                      <div className="mt-3 min-w-0 lg:mt-0">
                        {p.brand && (
                          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
                            {p.brand}
                          </p>
                        )}
                        <Link
                          href={`/product/${p.slug}`}
                          className="block pr-6 text-sm font-semibold leading-5 text-ink hover:text-accent"
                        >
                          {p.name}
                        </Link>
                        <div className="mt-2">
                          <ProductAvailability stock={p.stock} stockQty={p.stockQty} />
                        </div>
                        <p className="mt-2 font-display text-xl font-bold text-ink sm:text-2xl">
                          {p.price.final != null
                            ? formatPrice(p.price.final)
                            : "Цена уточняется"}
                        </p>
                        <div className="mt-3 max-w-48">
                          <AddToCartButton
                            productId={p.id}
                            productSlug={p.slug}
                            stock={p.stock}
                            hasPrice={p.price.final != null}
                            fullWidth
                            showLabel
                          />
                        </div>
                      </div>
                    </article>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th
                  scope="row"
                  className="sticky left-0 z-10 border-b border-r border-line bg-raised px-3 py-3 text-left sm:px-5"
                >
                  <span className="inline-flex items-center gap-2 font-semibold text-ink">
                    <SlidersHorizontal className="h-4 w-4 text-accent" aria-hidden />
                    <span className="hidden sm:inline">Характеристики</span>
                    <span className="sm:hidden">Параметры</span>
                  </span>
                </th>
                <td
                  colSpan={products.length}
                  className="border-b border-line bg-raised px-4 py-3 text-xs text-ink-3"
                >
                  Различающиеся значения подсвечены
                </td>
              </tr>
              {visibleRows.map((row) => (
                <tr key={row.label} className="group">
                  <th
                    scope="row"
                    className={cn(
                      "sticky left-0 z-10 border-b border-r border-line px-3 py-3.5 text-left font-normal leading-5 sm:px-5",
                      row.differs ? "bg-accent/10 text-ink" : "bg-surface text-ink-3",
                    )}
                  >
                    <span className="flex items-start gap-2">
                      {row.differs && (
                        <span
                          className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent"
                          aria-hidden
                        />
                      )}
                      {row.label}
                    </span>
                  </th>
                  {row.values.map((value, i) => (
                    <td
                      key={`${row.label}-${i}`}
                      className={cn(
                        "border-b border-r border-line px-3 py-3.5 leading-5 transition-colors sm:px-5",
                        row.differs
                          ? "bg-accent/5 font-medium text-ink group-hover:bg-accent/10"
                          : "text-ink-2 group-hover:bg-raised/60",
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
          </table>
        </div>

        {onlyDiff && visibleRows.length === 0 && (
          <p className="border-t border-line bg-raised/50 p-6 text-center text-sm text-ink-2">
            По заполненным характеристикам товары одинаковы.
          </p>
        )}
      </div>
    </section>
  );
}

/**
 * Собрать строки таблицы: объединение характеристик всех товаров.
 *
 * Порядок — как у первого товара, чтобы таблица не перетасовывалась при
 * удалении колонок; характеристики, которых у него нет, добавляются следом.
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

  return labels.map((label) => {
    const values = products.map((p) => p.specs.find((s) => s.label === label)?.value);
    const filled = values.filter((v): v is string => Boolean(v));
    const differs = filled.length !== values.length || new Set(filled).size > 1;
    return { label, values, differs };
  });
}
