// Оформление разделов каталога: предметное фото для карточек индекса и контурный
// чертёж-скелетон для hero страницы категории. В API картинки раздела пока нет,
// поэтому иллюстрация подбирается по витринному названию — само название, ссылка
// и состав всегда приходят с backend. Незнакомый раздел останется без картинки
// (в вёрстке есть нейтральный fallback), так что расширение дерева на backend
// не требует срочной правки frontend.

type Artwork = { photo?: string; skeleton?: string };

// Порядок важен: перфораторы проверяются до общего «электроинструмента»,
// иначе подкатегория получила бы чертёж шуруповёрта.
const RULES: Array<[RegExp, Artwork]> = [
  [/перфоратор/, { photo: "electroinstrument.webp", skeleton: "perforatory.png" }],
  [/оснаст|расход/, { photo: "osnastka.webp", skeleton: "osnastka.png" }],
  [/электроинструмент/, { photo: "electroinstrument.webp", skeleton: "electroinstrument.png" }],
  [/ручн/, { photo: "ruchnoy.webp", skeleton: "ruchnoy.png" }],
  [/авто|гараж/, { photo: "avto-garage.webp", skeleton: "avto-garage.png" }],
  [/измер/, { photo: "izmeritelnyy.webp", skeleton: "izmeritelnyy.png" }],
  [/крепёж|метиз/, { photo: "krepezh.webp", skeleton: "krepezh.png" }],
  [/электрик|освещ/, { photo: "electrika.webp", skeleton: "electrika.png" }],
  [/спецодеж|сиз/, { photo: "siz.webp", skeleton: "siz.png" }],
  [/садов/, { photo: "sadovaya.webp", skeleton: "sadovaya.png" }],
  [/силов|пневм|компресс/, { photo: "silovaya.webp", skeleton: "silovaya.png" }],
  [/свароч/, { photo: "svarochnaya.webp", skeleton: "svarochnaya.png" }],
  [/хранен|организац/, { photo: "hranenie.webp", skeleton: "hranenie.png" }],
  [/строитель|отделоч/, { photo: "stroitelnyy.webp", skeleton: "stroitelnyy.png" }],
  [/запчаст|аккумулятор|комплектующ/, { photo: "zapchasti.webp", skeleton: "zapchasti.png" }],
];

function match(name: string): Artwork | null {
  const value = name.toLocaleLowerCase("ru-RU");
  return RULES.find(([pattern]) => pattern.test(value))?.[1] ?? null;
}

/** Предметное фото раздела для карточек индекса каталога. */
export function categoryPhoto(name: string): string | null {
  const photo = match(name)?.photo;
  return photo ? `/catalog/categories/${photo}` : null;
}

/** Контурный чертёж раздела (1200×520, прозрачный фон) для hero категории. */
export function categorySkeleton(name: string): string | null {
  const skeleton = match(name)?.skeleton;
  return skeleton ? `/catalog/skeletons/${skeleton}` : null;
}

/**
 * Картинка типа инструмента для плитки навигации (DRF-996).
 *
 * Это фотографии товаров из нашего же каталога, обрезанные по предмету и с убранным
 * фоном (`scripts/tool_type_tile.py`) — так же, как их видит покупатель в выдаче.
 * Ключ — slug типа из nav-фасета.
 *
 * В карте только те типы, для которых нашлось ЧИСТОЕ фото. Каталожные снимки сняты
 * на разном фоне: у части кадров подложка не отделяется от инструмента, и плитка
 * получалась бы со светлым прямоугольником вокруг предмета — особенно заметно в
 * тёмной теме. Плитка без картинки рендерится текстом и выглядит законченной, а
 * грязная картинка выглядит поломкой, поэтому пустая строка карты — осознанный
 * выбор, а не недоделка. Сейчас без картинок остаются «Фрезеры», «Штроборезы» и
 * «Строительные пылесосы»: у первых нет чистого кадра, у остальных двух в каталоге
 * фотографий нет вовсе.
 */
const TOOL_TYPE_ARTWORK: Record<string, string> = {
  "dreli-shurupoverty": "dreli-shurupoverty.webp",
  shlifmashiny: "shlifmashiny.webp",
  pily: "pily.webp",
  perforatory: "perforatory.webp",
  "bolgarki-ushm": "bolgarki-ushm.webp",
  gaikoverty: "gaikoverty.webp",
  lobziki: "lobziki.webp",
  feny: "feny.webp",
  gravery: "gravery.webp",
};

export function toolTypeArtwork(slug: string): string | null {
  const file = TOOL_TYPE_ARTWORK[slug];
  return file ? `/catalog/tool-types/${file}` : null;
}
