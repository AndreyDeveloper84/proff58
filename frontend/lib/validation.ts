// Лёгкая валидация контактных полей checkout (#246). Бэк тоже валидирует (EmailField и пр.),
// это — быстрая клиентская проверка до отправки, чтобы не гонять заведомо неверную форму.

// Базовая проверка e-mail: один @, домен с точкой, без пробелов. Не RFC-полная — и не нужно.
export function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

// Только цифры из строки телефона (для подсчёта длины и нормализации).
function digitsOf(value: string): string {
  return value.replace(/\D/g, "");
}

// Российский номер: 11 цифр (7/8 + код + номер) либо 10 цифр (без ведущей 7/8).
export function isValidPhone(value: string): boolean {
  const d = digitsOf(value);
  if (d.length === 11) return d.startsWith("7") || d.startsWith("8");
  return d.length === 10;
}

// ИНН: 10 цифр — юрлицо, 12 — ИП. Зеркалит серверный _INN_RE (apps/orders/invoice.py),
// чтобы форма не отправляла заведомо отклоняемые B2B-реквизиты.
export function isValidInn(value: string): boolean {
  return /^\d{10}$|^\d{12}$/.test(value.trim());
}

// ИНН из 10 цифр = юрлицо → КПП обязателен (у ИП с ИНН из 12 цифр — нет).
export function isLegalEntityInn(value: string): boolean {
  return /^\d{10}$/.test(value.trim());
}

// КПП: ровно 9 цифр. Зеркалит серверный _KPP_RE.
export function isValidKpp(value: string): boolean {
  return /^\d{9}$/.test(value.trim());
}

// Нормализация к виду +7XXXXXXXXXX (на сервер уходит уже единообразно).
export function normalizePhone(value: string): string {
  const d = digitsOf(value);
  if (d.length === 11) return `+7${d.slice(1)}`;
  if (d.length === 10) return `+7${d}`;
  return value.trim();
}
