// Единый источник контента шапки/подвала. Чистые данные (без JSX).
// TODO: в будущем заменить на данные из SiteSettings.contacts/requisites через BFF.
export const SITE = {
  brand: { name: "Профессионал", tagline: "территория инструмента" },
  region: "Пенза",
  phone: { display: "8 (800) 600-44-99", href: "tel:+78006004499" },
  phoneNote: "Бесплатно по России", // #586: подпись под телефоном в шапке
  schedule: "Пн–Вс 09:00–20:00",
  email: "info@proff58.ru", // TODO: SiteSettings
  address: "г. Пенза, 1-й Онежский проезд, 12", // TODO: SiteSettings

  // #586: шапка по утверждённому макету главной.
  header: {
    tagline: "магазин инструментов", // подпись под логотипом
    store: "Магазин на 1-м Онежском проезде, 12", // адрес магазина в topbar (из SITE.address)
    catalogLabel: "Каталог товаров",
    searchPlaceholder: "Поиск по каталогу",
    // Инфо-пункты topbar. Страниц под них пока нет (не ссылки), но при наведении
    // каждый раскрывает своё подменю с краткой информацией — сюда переехал контент
    // сервисной полосы главной. href появится вместе со статическими страницами.
    // Пункт «Контакты» рендерит данные из SiteSettings (storefront), menu пустой.
    topLinks: [
      {
        label: "Сервис и ремонт",
        menu: [
          { title: "Сервисный центр", text: "Диагностика и обслуживание инструмента" },
          { title: "Проверим совместимость", text: "Оснастки и инструмента" },
          { title: "Помощь в подборе", text: "Подберём лучшее решение под задачу" },
        ],
      },
      {
        label: "Доставка и оплата",
        menu: [
          { title: "Самовывоз сегодня", text: "При заказе до 15:00" },
          { title: "Быстрая доставка", text: "По Пензе и области" },
          { title: "Оплата", text: "Картой онлайн, наличными, безналичный расчёт (B2B)" },
        ],
      },
      {
        label: "Гарантии",
        menu: [
          { title: "Официальная гарантия", text: "На весь ассортимент магазина" },
          { title: "Возврат за 14 дней", text: "Обмен и возврат без лишних вопросов" },
        ],
      },
      { label: "Контакты", menu: [] },
    ],
  },

  // Консультация в мессенджере MAX — блок помощи с выбором на страницах каталога.
  // TODO: SiteSettings — вынести ссылку/тексты в настройки сайта (сейчас статично).
  support: {
    max: {
      title: "Консультация в MAX",
      text: "Подберём инструмент под вашу задачу и бюджет",
      ctaLabel: "Написать специалисту",
      href: "https://max.ru/", // TODO: реальный deeplink магазина в MAX
    },
  },

  // #592: старое topNav удалено — единственный потребитель (TopBar.tsx) был
  // мёртвым кодом со ссылками на несуществующие страницы.

  // Иконка — строковый ключ (маппинг в Footer): shield|truck|undo|wrench|gift.
  trustBadges: [
    { icon: "shield", label: "Официальная гарантия" },
    { icon: "truck", label: "Быстрая доставка" },
    { icon: "undo", label: "Возврат за 14 дней" },
    { icon: "wrench", label: "Сервисный центр" },
    { icon: "gift", label: "Программа лояльности" },
  ],

  // #591: только РАБОЧИЕ маршруты — инфо-страниц (/delivery, /about, /faq …)
  // на сайте нет, битые ссылки в подвале не рисуем. Группы «Компания»/«Покупателям»
  // из макета появятся вместе со статическими страницами (см. MR).
  // Колонка «Каталог товаров» здесь не задаётся: раньше это были шесть подписей,
  // каждая из которых вела на общий /catalog — меню, которое никуда не ведёт.
  // Теперь разделы приходят из дерева категорий (lib/footer-nav.ts).
  footerColumns: [
    {
      title: "Покупателям",
      links: [
        { label: "Личный кабинет", href: "/account/profile" },
        { label: "Мои заказы", href: "/account/orders" },
        { label: "Избранное", href: "/account/wishlist" },
        { label: "Корзина", href: "/cart" },
      ],
    },
    {
      title: "Помощь",
      links: [
        { label: "Поиск по каталогу", href: "/search" },
        { label: "Подбор инструмента", href: "/catalog" },
        { label: "Статьи и обзоры", href: "/articles" },
      ],
    },
  ],

  // #591: описание магазина в левом блоке подвала.
  footerAbout:
    "Профессиональный инструмент с экспертной поддержкой в Пензе. Подберём, доставим, обслужим.",

  payments: ["Картой онлайн", "Наличными", "Безналичный (B2B)", "При получении"],
} as const;

export type ResolvedStorefront = {
  region: string;
  address: string;
  store: string;
  schedule: string;
  email: string;
  phone: { display: string; href: string };
  phoneNote: string;
  maxHref: string;
};

// SiteSettings.contacts — JSONField без жёсткой схемы. Поддерживаем только
// перечисленные публичные строковые ключи; неизвестные значения не попадают в UI.
export function resolveStorefront(input?: {
  region?: string;
  contacts?: Record<string, unknown>;
}): ResolvedStorefront {
  const contacts = input?.contacts ?? {};
  const text = (...keys: string[]): string => {
    for (const key of keys) {
      const value = contacts[key];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return "";
  };
  const display = text("phone_display", "phone") || SITE.phone.display;
  const digits = display.replace(/\D/g, "");
  const inferredHref = digits ? `tel:+${digits.replace(/^8(?=\d{10}$)/, "7")}` : SITE.phone.href;
  const address = text("address", "store_address") || SITE.address;

  return {
    region: input?.region?.trim() || SITE.region,
    address,
    store: text("store", "store_label") || `Магазин: ${address.replace(/^г\.\s*Пенза,\s*/i, "")}`,
    schedule: text("schedule", "working_hours") || SITE.schedule,
    email: text("email") || SITE.email,
    phone: {
      display,
      href: text("phone_href") || inferredHref,
    },
    phoneNote: text("phone_note") || SITE.phoneNote,
    maxHref: text("max_url", "max_href") || SITE.support.max.href,
  };
}
