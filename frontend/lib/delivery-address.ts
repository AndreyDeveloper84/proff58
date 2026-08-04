/**
 * Адрес доставки: отдельные поля формы ↔ одна строка для заказа.
 *
 * Раньше в оформлении было одно поле «Адрес доставки», и покупатели заполняли
 * его обрывками — в базе лежат заказы с адресом «Пен» и «Молокова», по которым
 * курьеру ехать некуда. Разложенные поля показывают, чего именно не хватает, и
 * проверяются по отдельности.
 *
 * На сервер по-прежнему уходит одна строка `delivery_address`: она же попадает
 * в 1С и в печатные формы, и менять этот контракт ради формы незачем.
 */

export type AddressParts = {
  city: string;
  street: string;
  house: string;
  flat?: string;
  entrance?: string;
  floor?: string;
};

/** Собрать человекочитаемый адрес: «г. Пенза, ул. Ленина, д. 12, кв. 5». */
export function composeAddress(parts: AddressParts): string {
  const chunks = [
    prefixed("г.", parts.city),
    // Улицу не переименовываем в «ул.»: покупатель мог написать «проспект
    // Победы» или «1-й Онежский проезд» — приставка сделала бы «ул. проспект».
    parts.street.trim(),
    prefixed("д.", parts.house),
    prefixed("кв.", parts.flat),
    prefixed("подъезд", parts.entrance),
    prefixed("этаж", parts.floor),
  ];
  return chunks.filter(Boolean).join(", ");
}

function prefixed(label: string, value: string | undefined): string {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return "";
  // Если человек уже написал приставку сам («г. Пенза», «д. 12») — не дублируем.
  const normalized = trimmed.toLowerCase();
  const bare = label.replace(".", "").toLowerCase();
  return normalized.startsWith(`${bare}.`) || normalized.startsWith(`${bare} `)
    ? trimmed
    : `${label} ${trimmed}`;
}

/**
 * Чего не хватает для доставки. null — всё в порядке.
 *
 * Возвращаем текст, а не список полей: форма показывает одну ошибку за раз, и
 * «Укажите улицу» полезнее, чем «форма заполнена неверно».
 */
export function validateAddress(parts: AddressParts): string | null {
  if (!parts.city.trim()) return "Укажите город доставки.";
  if (!parts.street.trim()) return "Укажите улицу.";
  if (!parts.house.trim()) return "Укажите номер дома — без него курьер не найдёт адрес.";
  return null;
}
