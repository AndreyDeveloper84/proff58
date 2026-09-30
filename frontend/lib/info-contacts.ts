import type { ResolvedStorefront } from "./site";

// Подстановка контактов магазина в инфо-страницы из кода (lib/info-content.ts).
//
// Тексты страниц едут с релизом, а телефон, адрес, почта и график — из настроек
// сайта, как в шапке и подвале (DRF-2495). В тексте стоят метки вида {{phone}};
// здесь они заменяются значениями из resolveStorefront (при недоступном API — его
// запасные значения из SITE, то есть страница не ломается).
//
// Точка магазина на карте задана координатами (STORE_MAP в lib/site.ts), а не
// адресом: сменили адрес в настройках — координаты карты правятся в коде.

const TOKEN = /\{\{(\w+)\}\}/g;

export function contactValues(storefront: ResolvedStorefront): Record<string, string> {
  return {
    address: storefront.address,
    schedule: storefront.schedule,
    phone: storefront.phone.display,
    phone_href: storefront.phone.href,
    email: storefront.email,
  };
}

/**
 * Копия `value`, где во всех строках (на любой глубине) метки заменены
 * контактами. Замена в один проход: значение из настроек, в котором вдруг
 * окажется «{{…}}», повторно не раскрывается. Хвостовая точка у значения
 * срезается — в тексте после метки своя пунктуация («{{address}}. …»).
 * Неизвестная метка остаётся как есть — её ловит тест.
 */
export function fillContacts<T>(value: T, storefront: ResolvedStorefront): T {
  const values = contactValues(storefront);
  const fill = (node: unknown): unknown => {
    if (typeof node === "string") {
      return node.replace(TOKEN, (token, key: string) =>
        Object.hasOwn(values, key) ? values[key].replace(/[.\s]+$/, "") : token,
      );
    }
    if (Array.isArray(node)) return node.map(fill);
    if (node && typeof node === "object") {
      return Object.fromEntries(Object.entries(node).map(([key, item]) => [key, fill(item)]));
    }
    return node;
  };
  return fill(value) as T;
}
