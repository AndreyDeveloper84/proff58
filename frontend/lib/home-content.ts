// Контент главной страницы, которого НЕТ в API каталога: тексты, промо, ссылки,
// картинки сценарных карточек. Смена копий магазина — правка ТОЛЬКО этого файла,
// без касания компонентов. Названия категорий и сами товары приходят из API.

export type HeroBullet = { icon: string; text: string };
export type IntentCard = { image: string; title: string; text: string; href: string };
export type ServiceItem = { icon: string; title: string; text: string };

export const HOME_CONTENT = {
  // #592: nav/account удалены — потреблялись только старым тёмным Header
  // (до #586); «#»-ссылки в новых компонентах запрещены DoD эпика.
  // #587: hero по утверждённому макету — тёмный фотобаннер, экспертный подбор.
  hero: {
    titleLine1: "Профессиональный инструмент",
    titleLine2: "с экспертным подбором под вашу задачу",
    subtitle:
      "Оригинальная продукция, в наличии в Пензе, сервисный центр и быстрая доставка. " +
      "Подберём оптимальное решение под ваш проект и бюджет.",
    bullets: [
      { icon: "ShieldCheck", text: "Оригинальная продукция" },
      { icon: "Truck", text: "Быстрая доставка и самовывоз" },
      { icon: "Users", text: "Помощь экспертов в подборе" },
      { icon: "Wrench", text: "Сервисный центр в Пензе" },
    ] as HeroBullet[],
  },
  // #588: сценарный вход «Что вы хотите сделать?» — помогает выбрать по задаче,
  // не думая в терминах дерева каталога. Ссылки ведут в каталог (маппинг на
  // конкретные разделы/поиск — follow-up, когда закрепим taxonomy-маршруты).
  intent: {
    title: "Что вы хотите сделать?",
    cards: [
      {
        image: "/home/intent/home.webp",
        title: "Для дома",
        text: "Ремонт, сад, мебель, бытовые задачи",
        href: "/catalog/ruchnoy",
      },
      {
        image: "/home/intent/renovation.webp",
        title: "Ремонт квартиры",
        text: "Отделка, электрика, сантехника",
        href: "/catalog/stroitelnyy",
      },
      {
        image: "/home/intent/construction.webp",
        title: "Стройка и бетон",
        text: "Фундамент, стены, бетонные работы",
        href: "/catalog/elektroinstrument",
      },
      {
        image: "/home/intent/professional.webp",
        title: "Профессиональная работа",
        text: "Ежедневные нагрузки, интенсивное использование",
        href: "/catalog/silovaya",
      },
      {
        image: "/home/intent/consumables.webp",
        title: "Расходные материалы и оснастка",
        text: "Буры, диски, свёрла, расходники",
        href: "/catalog/osnastka",
      },
    ] as IntentCard[],
  },
  // Сервисная полоса удалена с главной: её содержимое переехало в выпадающие
  // подменю инфо-пунктов topbar (SITE.header.topLinks, lib/site.ts).

  // #589: популярные бренды (curated). Логотипов-ассетов пока нет — карточки
  // текстовые (структура позволяет добавить image später). Ссылка — поиск по
  // бренду: отдельного маршрута «все товары бренда» нет, /search?q= работает.
  popularBrands: [
    "Makita",
    "Bosch",
    "DeWALT",
    "Metabo",
    "AEG",
    "Milwaukee",
    "Hilti",
    "Stanley",
    "Ресанта",
  ] as string[],

  // #590: «Почему покупают у нас» — 6 пунктов по макету.
  whyBuy: [
    { icon: "Award", title: "Более 10 лет", text: "на рынке Пензы" },
    { icon: "ShieldCheck", title: "Только оригинальные", text: "товары от официальных поставщиков" },
    { icon: "Users", title: "Экспертная помощь", text: "в подборе инструмента под задачу и бюджет" },
    { icon: "Wrench", title: "Сервисный центр", text: "диагностика, ремонт, запчасти в наличии" },
    { icon: "BadgeRussianRuble", title: "Выгодные цены", text: "честные цены и акции для наших клиентов" },
    { icon: "RotateCcw", title: "Гарантия и возврат", text: "официальная гарантия и простой возврат" },
  ] as ServiceItem[],
};
