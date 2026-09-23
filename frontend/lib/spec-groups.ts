// Разделы технического паспорта: одна раскладка характеристик для карточки товара
// и таблицы сравнения. Если разделы разойдутся, человек, сравнивающий два
// перфоратора, будет искать «Патрон» не там, где видел его на странице товара.
import { CircleGauge, PackageCheck, PlugZap, Wrench, type LucideIcon } from "lucide-react";

import type { ProductSpec } from "./types";

export type SpecGroup = {
  title: string;
  icon: LucideIcon;
  specs: ProductSpec[];
};

const GROUPS = [
  {
    title: "Производительность",
    icon: CircleGauge,
    test:
      /мощност|энерги|частот|оборот|скорост|производительност|давлен|расход|усили|диаметр|глубин|крутящ/i,
  },
  {
    title: "Оснастка",
    icon: Wrench,
    test: /патрон|оснаст|креплен|насад|режим|реверс|муфт|комплект|кейс|диск|бур|сверл/i,
  },
  {
    title: "Питание и корпус",
    icon: PlugZap,
    test: /питан|напряжен|аккумулятор|ёмкост|емкост|кабел|вес|размер|габарит|материал|корпус|длин|ширин|высот/i,
  },
] as const;

/**
 * Разложить характеристики по разделам.
 *
 * Раздел выбирается по подписи (первое совпадение по порядку GROUPS), всё
 * неопознанное уходит в «Дополнительно». Пустые разделы не возвращаются —
 * заголовок без строк под ним читается как потерянные данные.
 */
export function groupProductSpecs(specs: ProductSpec[]): SpecGroup[] {
  const buckets = GROUPS.map((group) => ({ ...group, specs: [] as ProductSpec[] }));
  const other: ProductSpec[] = [];

  for (const spec of specs) {
    const bucket = buckets.find((group) => group.test.test(spec.label));
    (bucket?.specs ?? other).push(spec);
  }

  return [
    ...buckets.map(({ title, icon, specs: groupedSpecs }) => ({
      title,
      icon,
      specs: groupedSpecs,
    })),
    { title: "Дополнительно", icon: PackageCheck, specs: other },
  ].filter((group) => group.specs.length > 0);
}
