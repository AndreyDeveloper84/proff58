import type { CategoryNode } from "./adapters";

/**
 * Разделы каталога для подвала.
 *
 * Раньше колонка «Каталог товаров» была шестью подписями из site.ts, и все шесть
 * вели на общий /catalog: разделов с такими названиями в дереве не было, а рисовать
 * битые ссылки не хотели. Для человека это выглядело как неработающее меню.
 *
 * Теперь берём настоящие корневые разделы из дерева категорий: адреса ведут в
 * раздел, а подписи приходят из админки и не разъезжаются с сайтом.
 */
export type FooterCategoryLink = { label: string; href: string };

/** Сколько разделов показываем — колонка подвала узкая, длинный список её ломает. */
export const FOOTER_CATEGORY_LIMIT = 4;

/**
 * Какие разделы показывать. Порядок — по числу опубликованных товаров на замере
 * 03.08.2026: оснастка 4848, ручной 2487, электроинструмент 1518, строительный 938
 * (всего корневых разделов 14). Список зафиксирован здесь, а не считается на лету:
 * счётчика товаров в /api/catalog/categories/ нет, а агрегат по поддереву на каждый
 * рендер подвала — запрос по всему каталогу на каждой странице сайта.
 * Пересматривать, когда состав каталога заметно изменится.
 */
export const FOOTER_CATEGORY_SLUGS = [
  "osnastka",
  "ruchnoy",
  "elektroinstrument",
  "stroitelnyy",
];

/**
 * Выбрать разделы для подвала из дерева категорий.
 *
 * Приоритетные slug'и берём в заданном порядке; если раздел переименовали, сняли
 * с сайта или переставили — добираем ближайшими корнями дерева, чтобы в подвале не
 * оказалось две ссылки вместо четырёх. Дерево недоступно → пустой список, и подвал
 * покажет только «Все категории».
 */
export function pickFooterCategories(tree: CategoryNode[] | null): FooterCategoryLink[] {
  if (!tree || tree.length === 0) return [];

  const bySlug = new Map(tree.map((node) => [node.slug, node]));
  const picked: CategoryNode[] = [];

  for (const slug of FOOTER_CATEGORY_SLUGS) {
    const node = bySlug.get(slug);
    if (node && !picked.includes(node)) picked.push(node);
  }
  for (const node of tree) {
    if (picked.length >= FOOTER_CATEGORY_LIMIT) break;
    if (!picked.includes(node)) picked.push(node);
  }

  return picked
    .slice(0, FOOTER_CATEGORY_LIMIT)
    .map((node) => ({ label: node.name, href: `/catalog/${node.slug}` }));
}
