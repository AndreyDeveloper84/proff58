"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Trash2, X } from "lucide-react";

import { COMPARE_LIMIT, useCompare } from "@/lib/compare";
import { formatPrice } from "@/lib/format";
import type { ProductDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ProductImage } from "@/components/product/ProductImage";
import { AddToCartButton } from "@/components/product/AddToCartButton";
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
    return <ErrorState description="Не удалось загрузить товары для сравнения." />;
  }
  if (slugs.length > 0 && products === null) {
    return <LoadingState label="Загружаем товары…" />;
  }
  if (slugs.length === 0 || products === null || products.length === 0) {
    return (
      <EmptyState
        title="В сравнении пока пусто"
        description={`Добавьте товары кнопкой сравнения в каталоге или на странице товара — до ${COMPARE_LIMIT} штук.`}
        action={
          <Link
            href="/catalog"
            className="inline-flex h-11 items-center rounded-md bg-accent px-4 text-sm font-medium text-accent-ink"
          >
            Перейти в каталог
          </Link>
        }
      />
    );
  }

  const rows = buildRows(products);
  const visibleRows = onlyDiff ? rows.filter((r) => r.differs) : rows;
  const diffCount = rows.filter((r) => r.differs).length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={onlyDiff}
            onChange={(e) => setOnlyDiff(e.target.checked)}
            className="h-4 w-4 accent-[var(--accent)]"
          />
          Только различия
          <span className="text-ink-3">({diffCount})</span>
        </label>
        <button
          type="button"
          onClick={clear}
          className="inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-danger"
        >
          <Trash2 className="h-4 w-4" aria-hidden />
          Очистить список
        </button>
      </div>

      {/* Прокручивается сама таблица, а не страница: горизонтальный скролл всего
          документа ломает чтение остальной витрины. */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <caption className="sr-only">Сравнение характеристик выбранных товаров</caption>
          <thead>
            <tr>
              <th scope="row" className="w-40 border-b border-line p-2 text-left align-top" />
              {products.map((p) => (
                <th
                  key={p.slug}
                  scope="col"
                  className="min-w-[180px] border-b border-line p-2 text-left align-top font-normal"
                >
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => remove(p.slug)}
                      aria-label={`Убрать ${p.name} из сравнения`}
                      className="absolute right-0 top-0 grid h-8 w-8 place-items-center rounded-full text-ink-3 hover:text-danger"
                    >
                      <X className="h-4 w-4" aria-hidden />
                    </button>
                    <a href={`/product/${p.slug}`} className="block w-28">
                      <ProductImage src={p.images[0]?.url} alt={p.name} />
                    </a>
                    <a
                      href={`/product/${p.slug}`}
                      className="mt-2 block text-sm font-medium text-ink hover:text-accent"
                    >
                      {p.name}
                    </a>
                    <p className="mt-1 font-display text-lg font-bold text-ink">
                      {p.price.final != null ? formatPrice(p.price.final) : "Цена уточняется"}
                    </p>
                    <div className="mt-2">
                      <AddToCartButton
                        productId={p.id}
                        productSlug={p.slug}
                        stock={p.stock}
                        hasPrice={p.price.final != null}
                        fullWidth
                      />
                    </div>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={row.label} className={cn(row.differs && "bg-accent/5")}>
                <th scope="row" className="border-b border-line p-2 text-left font-normal text-ink-3">
                  {row.label}
                </th>
                {row.values.map((value, i) => (
                  <td key={`${row.label}-${i}`} className="border-b border-line p-2 text-ink-2">
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
        <p className="mt-4 rounded-lg border border-line bg-surface p-6 text-center text-ink-2">
          По заполненным характеристикам товары одинаковы.
        </p>
      )}
    </div>
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
