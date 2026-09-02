// Единый источник контента шапки/подвала. Чистые данные (без JSX).
// TODO: в будущем заменить на данные из SiteSettings.contacts/requisites через BFF.
/** Пункт служебной полосы шапки. `href` есть не у каждого: у части пунктов
    страницы нет вовсе, и тогда пункт остаётся подсказкой (см. Header). */
export type TopLink = {
  label: string;
  href?: string;
  // readonly: SITE объявлен `as const`, и вложенные массивы там неизменяемые.
  menu: readonly { title: string; text: string; href?: string }[];
};

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
    // Инфо-пункты topbar: при наведении каждый раскрывает подсказку — сюда переехал
    // контент сервисной полосы главной. Адреса ведут на страницы из админки, но
    // ссылкой пункт становится ТОЛЬКО если страница опубликована (DRF-1442):
    // страницы заводятся черновиками, и ссылка на черновик дала бы 404 из шапки на
    // каждой странице сайта. Проверку делает Header, здесь — только намерение.
    // Пункт «Контакты» рендерит данные из SiteSettings (storefront), menu пустой.
    topLinks: [
      {
        label: "Сервис и ремонт",
        href: "/info/warranty",
        menu: [
          {
            title: "Сервисный центр",
            text: "Диагностика и обслуживание инструмента",
            href: "/info/warranty",
          },
          { title: "Проверим совместимость", text: "Оснастки и инструмента" },
          { title: "Помощь в подборе", text: "Подберём лучшее решение под задачу" },
        ],
      },
      {
        label: "Доставка и оплата",
        href: "/info/delivery",
        menu: [
          { title: "Самовывоз сегодня", text: "При заказе до 15:00", href: "/info/delivery" },
          { title: "Быстрая доставка", text: "По Пензе и области", href: "/info/delivery" },
          {
            title: "Оплата",
            text: "Картой онлайн, наличными, безналичный расчёт (B2B)",
            href: "/info/payment",
          },
        ],
      },
      {
        label: "Гарантии",
        href: "/info/warranty",
        menu: [
          {
            title: "Официальная гарантия",
            text: "На весь ассортимент магазина",
            href: "/info/warranty",
          },
          { title: "Возврат за 14 дней", text: "Обмен и возврат без лишних вопросов" },
        ],
      },
      // «Контакты» ведут на «О компании»: там адрес, режим и карта проезда.
      { label: "Контакты", href: "/info/about", menu: [] },
    ],
  },

  // Бот магазина в мессенджере MAX. Тексты описывают то, что бот действительно
  // умеет: вход без пароля и уведомления по заказу и поступлению товара. Живого
  // консультанта за ним нет, и обещать «напишите специалисту» нельзя — человек
  // напишет и не дождётся ответа.
  //
  // Ссылки здесь намеренно НЕТ: адрес бота приходит с сервера (max_bot_url в
  // /api/core/theme/, собирается из MAX_BOT_USERNAME). Захардкоженный
  // https://max.ru/ вёл на главную мессенджера и выглядел рабочим.
  maxBot: {
    title: "Наш бот в MAX",
    text: "Вход без пароля и уведомления о заказе",
  },

  // #592: старое topNav удалено — единственный потребитель (TopBar.tsx) был
  // мёртвым кодом со ссылками на несуществующие страницы.


  // #591: только РАБОЧИЕ маршруты — битые ссылки в подвале не рисуем.
  // Инфо-страницы («О компании», «Доставка», «Оплата», «Гарантийный ремонт»)
  // ведутся в админке и рисуются отдельной колонкой «Информация» по факту
  // публикации (Footer.tsx) — здесь их дублировать не нужно.
  // Разделы ведут в СВОИ разделы, а не все в /catalog: ссылка с названием
  // раздела, открывающая общий каталог, — обманутое ожидание, человек второй раз
  // ищет то же самое руками. Slug'и — корневые узлы каталога (см. /api/catalog/categories/).
  //
  // Колонки «Покупателям» здесь нет: кабинет, заказы, избранное и корзина стоят
  // в шапке на каждой странице, и второй такой же список внизу — просто шум.
  footerColumns: [
    {
      title: "Каталог товаров",
      links: [
        { label: "Электроинструмент", href: "/catalog/elektroinstrument" },
        { label: "Ручной инструмент", href: "/catalog/ruchnoy" },
        { label: "Измерительный инструмент", href: "/catalog/izmeritelnyy" },
        { label: "Садовая техника", href: "/catalog/sadovaya" },
        { label: "Сварочное оборудование", href: "/catalog/svarka" },
        { label: "Все категории", href: "/catalog" },
      ],
    },
    {
      title: "Помощь",
      links: [
        { label: "Поиск по каталогу", href: "/search" },
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
  /** Бот магазина в MAX — собран сервером из MAX_BOT_USERNAME (может отсутствовать). */
  max_bot_url?: string;
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
    // Приоритет: явная ссылка из настроек сайта → бот из переменных окружения.
    // Пусто — плитка «наш бот в MAX» не рисуется (битую ссылку не показываем).
    maxHref: text("max_url", "max_href") || (input?.max_bot_url ?? "").trim(),
  };
}
