// Контент главной страницы, которого НЕТ в API каталога: тексты, статистика, телефон,
// промо, ссылки и визуальные ассеты категорий/hero. Перекраска/смена копий магазина —
// правка ТОЛЬКО этого файла, без касания компонентов. Названия категорий и сами товары
// приходят из API; здесь — лишь привязка slug→картинка и курируемый список «хитов».

export type HomeStat = { value: number; suffix: string; label: string };
export type TrustItem = { icon: string; title: string };
export type HeroBullet = { icon: string; text: string };
export type IntentCard = { icon: string; title: string; text: string; href: string };
export type ServiceItem = { icon: string; title: string; text: string };

export const HOME_CONTENT = {
  topbar: {
    promo: "Бесплатная доставка по Пензе от 5 000 ₽",
    phone: "8 (800) 600-44-99",
    phoneHref: "tel:+78006004499",
  },
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
    // primaryCta открывает модалку подбора (InquiryModal); secondary ведёт в каталог.
    primaryCta: { label: "Подобрать инструмент" },
    secondaryCta: { label: "Перейти в каталог", href: "/catalog" },
    maxPill: { title: "Консультация в MAX", note: "Подбор инструмента в чате за 2–3 минуты" },
  },
  // #588: сценарный вход «Что вы хотите сделать?» — помогает выбрать по задаче,
  // не думая в терминах дерева каталога. Ссылки ведут в каталог (маппинг на
  // конкретные разделы/поиск — follow-up, когда закрепим taxonomy-маршруты).
  intent: {
    title: "Что вы хотите сделать?",
    cards: [
      {
        icon: "Home",
        title: "Для дома",
        text: "Ремонт, сад, мебель, бытовые задачи",
        href: "/catalog/ruchnoy",
      },
      {
        icon: "Paintbrush",
        title: "Ремонт квартиры",
        text: "Отделка, электрика, сантехника",
        href: "/catalog/stroitelnyy",
      },
      {
        icon: "Hammer",
        title: "Стройка и бетон",
        text: "Фундамент, стены, бетонные работы",
        href: "/catalog/elektroinstrument",
      },
      {
        icon: "Briefcase",
        title: "Профессиональная работа",
        text: "Ежедневные нагрузки, интенсивное использование",
        href: "/catalog/silovaya",
      },
      {
        icon: "Cog",
        title: "Расходные материалы и оснастка",
        text: "Буры, диски, свёрла, расходники",
        href: "/catalog/osnastka",
      },
    ] as IntentCard[],
  },
  // #588: сервисная полоса преимуществ под сценариями.
  serviceStrip: [
    { icon: "MapPin", title: "Магазин в Пензе", text: "1-й Онежский проезд, 12" },
    { icon: "Truck", title: "Самовывоз сегодня", text: "при заказе до 15:00" },
    { icon: "Users", title: "Помощь в подборе", text: "подберём лучшее решение" },
    { icon: "CheckCircle2", title: "Проверим совместимость", text: "оснастки и инструмента" },
    { icon: "Wrench", title: "Сервис и ремонт", text: "диагностика и обслуживание" },
  ] as ServiceItem[],

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

  // slug корневой категории → фон плитки (плейсхолдеры; дизайнер заменит). Дефолт — ниже.
  categoryAssets: {} as Record<string, string>,
  // Курируемые «хиты»: slug'и товаров. Пусто → fallback на ?sort=new (см. lib/catalog.ts).
  bestsellerSlugs: [] as string[],
  trust: [
    { icon: "ShieldCheck", title: "Официальная гарантия" },
    { icon: "Truck", title: "Быстрая доставка" },
    { icon: "Store", title: "Самовывоз" },
    { icon: "Wrench", title: "Сервис и запчасти" },
    { icon: "Building2", title: "Работаем с юрлицами" },
  ] as TrustItem[],
  // #590: «Почему покупают у нас» — 6 пунктов по макету.
  whyBuy: [
    { icon: "Award", title: "Более 10 лет", text: "на рынке Пензы" },
    { icon: "ShieldCheck", title: "Только оригинальные", text: "товары от официальных поставщиков" },
    { icon: "Users", title: "Экспертная помощь", text: "в подборе инструмента под задачу и бюджет" },
    { icon: "Wrench", title: "Сервисный центр", text: "диагностика, ремонт, запчасти в наличии" },
    { icon: "BadgeRussianRuble", title: "Выгодные цены", text: "честные цены и акции для наших клиентов" },
    { icon: "RotateCcw", title: "Гарантия и возврат", text: "официальная гарантия и простой возврат" },
  ] as ServiceItem[],
  // #590: превью статей — раздела статей на сайте нет, поэтому карточки-заглушки
  // БЕЗ ссылок (не делаем битых href); появится раздел — станут ссылками.
  articles: {
    title: "Полезные статьи и обзоры",
    items: [
      {
        title: "Как выбрать шуруповёрт для дома и дачи",
        date: "18 мая 2026",
        image: "/home/hero/approved-tools-hero.png",
        imagePosition: "48% 58%",
      },
      {
        title: "Перфоратор или дрель: что выбрать?",
        date: "12 мая 2026",
        image: "/home/hero/approved-tools-hero.png",
        imagePosition: "61% 58%",
      },
      {
        title: "Топ-10 оснастки, которая должна быть у мастера",
        date: "6 мая 2026",
        image: "/home/hero/approved-tools-hero.png",
        imagePosition: "75% 62%",
      },
      {
        title: "Уход за инструментом: простые правила",
        date: "28 апреля 2026",
        image: "/home/hero/approved-tools-hero.png",
        imagePosition: "91% 58%",
      },
    ],
  },
  // #590: карточка MAX-помощи (правая колонка нижней зоны).
  maxHelp: {
    title: "Нужна помощь в подборе?",
    text: "Напишите нам в MAX — подберём лучшее решение за 2–3 минуты",
    cta: "Консультация в MAX",
  },
  // #590: email-подписка — UI-заглушка (backend подписок нет, решение зафиксировано):
  // поле и кнопка отрисованы, отправка отключена до появления backend.
  subscribe: {
    title: "Будьте в курсе новинок и акций",
    text: "Подпишитесь и получайте полезные советы и спецпредложения на почту",
    cta: "Подписаться",
    note: "Скоро: подписка заработает после запуска рассылки",
  },
  consult: {
    title: "Не знаете, какой инструмент выбрать?",
    text: "Поможем подобрать инструмент под вашу задачу, бюджет и условия работы.",
    maxUrl: "https://max.ru/proffinstrument",
  },
  about: {
    title: "О магазине «Профессионал»",
    text: "Магазин профессионального электро- и ручного инструмента с доставкой по Пензе и области.",
    stats: [
      { value: 10, suffix: "+", label: "лет на рынке" },
      { value: 20000, suffix: "+", label: "товаров в каталоге" },
      { value: 50000, suffix: "+", label: "довольных клиентов" },
      { value: 100, suffix: "+", label: "брендов" },
    ] as HomeStat[],
  },
};

// Фон плитки категории. Нет ассета для slug → нейтральный плейсхолдер.
export function categoryAsset(slug: string): string {
  return HOME_CONTENT.categoryAssets[slug] ?? "/home/categories/placeholder.svg";
}
