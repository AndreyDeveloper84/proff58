// Единый источник контента шапки/подвала. Чистые данные (без JSX).
// TODO: в будущем заменить на данные из SiteSettings.contacts/requisites через BFF.
export const SITE = {
  brand: { name: "Профессионал", tagline: "территория инструмента" },
  region: "Пенза",
  phone: { display: "8 (800) 600-44-99", href: "tel:+78006004499" },
  phoneNote: "Бесплатно по России", // #586: подпись под телефоном в шапке
  schedule: "Пн–Вс 09:00–20:00",
  email: "info@proff58.ru", // TODO: SiteSettings
  address: "г. Пенза, ул. Складская, 10", // TODO: SiteSettings

  // #586: шапка по утверждённому макету главной.
  header: {
    tagline: "магазин инструментов", // подпись под логотипом
    store: "Магазин на ул. Складская, 10", // адрес магазина в topbar (из SITE.address)
    catalogLabel: "Каталог товаров",
    searchPlaceholder: "Поиск по каталогу",
    // Инфо-пункты topbar. #592: страниц под них пока нет, поэтому Header
    // рендерит их future-текстом (не ссылками). href появится вместе со
    // статическими страницами.
    topLinks: [
      { label: "Сервис и ремонт" },
      { label: "Доставка и оплата" },
      { label: "Гарантии" },
      { label: "Контакты" },
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
  footerColumns: [
    {
      title: "Каталог товаров",
      links: [
        { label: "Электроинструмент", href: "/catalog" },
        { label: "Ручной инструмент", href: "/catalog" },
        { label: "Измерительный инструмент", href: "/catalog" },
        { label: "Садовая техника", href: "/catalog" },
        { label: "Сварочное оборудование", href: "/catalog" },
        { label: "Все категории", href: "/catalog" },
      ],
    },
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
      ],
    },
  ],

  // #591: описание магазина в левом блоке подвала.
  footerAbout:
    "Профессиональный инструмент с экспертной поддержкой в Пензе. Подберём, доставим, обслужим.",

  // Иконка — строковый ключ (маппинг в Footer): vk|telegram|youtube|whatsapp.
  socials: [
    { label: "ВКонтакте", href: "https://vk.com/", icon: "vk" }, // TODO
    { label: "Telegram", href: "https://t.me/", icon: "telegram" },
    { label: "YouTube", href: "https://youtube.com/", icon: "youtube" },
  ],

  payments: ["Картой онлайн", "Наличными", "Безналичный (B2B)", "При получении"],
} as const;
