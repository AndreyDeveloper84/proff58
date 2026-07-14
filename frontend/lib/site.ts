// Единый источник контента шапки/подвала. Чистые данные (без JSX).
// TODO: в будущем заменить на данные из SiteSettings.contacts/requisites через BFF.
export const SITE = {
  brand: { name: "Профессионал", tagline: "территория инструмента" },
  region: "Пенза",
  phone: { display: "8 (800) 600-44-99", href: "tel:+78006004499" },
  schedule: "Пн–Вс 9:00–20:00",
  email: "info@proff58.ru", // TODO: SiteSettings
  address: "г. Пенза, ул. Складская, 10", // TODO: SiteSettings

  // Консультация в мессенджере MAX — блок помощи с выбором на страницах каталога.
  // TODO: SiteSettings — вынести ссылку/тексты в настройки сайта (сейчас статично).
  support: {
    max: {
      title: "Нужна помощь с выбором?",
      text: "Подберём инструмент под вашу задачу — ответит живой специалист в MAX.",
      ctaLabel: "Спросить в MAX",
      href: "https://max.ru/", // TODO: реальный deeplink магазина в MAX
    },
  },

  // Верхнее меню инфо-панели.
  topNav: [
    { label: "Акции", href: "/promo" }, // TODO: маршруты-заглушки
    { label: "Доставка и оплата", href: "/delivery" },
    { label: "Гарантия", href: "/warranty" },
    { label: "Сервис", href: "/service" },
    { label: "Компания", href: "/about" },
    { label: "Контакты", href: "/contacts" },
  ],

  // Иконка — строковый ключ (маппинг в Footer): shield|truck|undo|wrench|gift.
  trustBadges: [
    { icon: "shield", label: "Официальная гарантия" },
    { icon: "truck", label: "Быстрая доставка" },
    { icon: "undo", label: "Возврат за 14 дней" },
    { icon: "wrench", label: "Сервисный центр" },
    { icon: "gift", label: "Программа лояльности" },
  ],

  footerColumns: [
    {
      title: "Каталог",
      links: [
        { label: "Электроинструмент", href: "/catalog" },
        { label: "Бензоинструмент", href: "/catalog" },
        { label: "Садовая техника", href: "/catalog" },
        { label: "Оснастка", href: "/catalog" },
      ],
    },
    {
      title: "Покупателю",
      links: [
        { label: "Доставка и оплата", href: "/delivery" },
        { label: "Гарантия", href: "/warranty" },
        { label: "Возврат", href: "/returns" },
        { label: "Вопросы и ответы", href: "/faq" },
      ],
    },
    {
      title: "Компания",
      links: [
        { label: "О магазине", href: "/about" },
        { label: "Контакты", href: "/contacts" },
        { label: "Сервисный центр", href: "/service" },
        { label: "Вакансии", href: "/jobs" },
      ],
    },
  ],

  // Иконка — строковый ключ (маппинг в Footer): vk|telegram|youtube|whatsapp.
  socials: [
    { label: "ВКонтакте", href: "https://vk.com/", icon: "vk" }, // TODO
    { label: "Telegram", href: "https://t.me/", icon: "telegram" },
    { label: "YouTube", href: "https://youtube.com/", icon: "youtube" },
  ],

  payments: ["Картой онлайн", "Наличными", "Безналичный (B2B)", "При получении"],
} as const;
