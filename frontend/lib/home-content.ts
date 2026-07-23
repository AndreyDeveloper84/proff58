// Контент главной страницы, которого НЕТ в API каталога: тексты, статистика, телефон,
// промо, ссылки и визуальные ассеты категорий/hero. Перекраска/смена копий магазина —
// правка ТОЛЬКО этого файла, без касания компонентов. Названия категорий и сами товары
// приходят из API; здесь — лишь привязка slug→картинка и курируемый список «хитов».

export type HomeStat = { value: number; suffix: string; label: string };
export type NavLink = { label: string; href: string };
export type TrustItem = { icon: string; title: string };
export type HeroBullet = { icon: string; text: string };

export const HOME_CONTENT = {
  topbar: {
    promo: "Бесплатная доставка по Пензе от 5 000 ₽",
    phone: "8 (800) 600-44-99",
    phoneHref: "tel:+78006004499",
  },
  nav: [
    { label: "Акции", href: "#" },
    { label: "Доставка и оплата", href: "#" },
    { label: "Гарантия", href: "#" },
    { label: "Сервис", href: "#" },
    { label: "Компания", href: "#" },
    { label: "Контакты", href: "#" },
  ] as NavLink[],
  account: [
    { label: "Личный кабинет", href: "/account/profile" },
    { label: "Избранное", href: "/account/wishlist" },
    // «Сравнение» — Wave 2, страницы пока нет (не даём мёртвую ссылку).
  ] as NavLink[],
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
