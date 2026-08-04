"use client";

// Избранное гостя — в localStorage, по образцу списка сравнения (lib/compare.ts).
//
// Почему без аккаунта. Сердечко жмут в момент интереса к товару, и требовать в
// этот момент регистрацию — значит терять и клик, и повод вернуться. Рядом на
// той же карточке кнопка сравнения уже работает без входа, так что запрет на
// избранное выглядел просто непоследовательностью.
//
// Плата за это — список живёт в одном браузере. Ровно так же ведёт себя
// сравнение, а при входе список переезжает в аккаунт (WishlistProvider) и
// становится общим для всех устройств.
//
// Храним id: сервер работает по ним же, и при переносе ничего резолвить не надо.

export const WISHLIST_STORAGE_KEY = "wishlist";

//: Потолок гостевого списка. Совпадает с MAX_WISHLIST_BULK на бэкенде — что
//: накопилось, то и должно перенестись при входе целиком.
export const WISHLIST_GUEST_LIMIT = 100;

const listeners = new Set<() => void>();

// useSyncExternalStore сравнивает снимки через Object.is: новый массив на каждый
// вызов увёл бы React в бесконечный ререндер. Держим разобранное в кэше.
let cache: number[] = [];
let cacheRaw: string | null = null;

const EMPTY: number[] = [];

export function readGuestWishlist(): number[] {
  try {
    const raw = localStorage.getItem(WISHLIST_STORAGE_KEY);
    if (raw === cacheRaw) return cache;
    cacheRaw = raw;
    const parsed = raw ? JSON.parse(raw) : [];
    cache = Array.isArray(parsed)
      ? parsed.filter((id) => typeof id === "number" && Number.isInteger(id) && id > 0)
      : [];
    return cache;
  } catch {
    // Приватный режим, отключённый storage или испорченный JSON — избранное
    // просто не сохраняется, но витрина не падает.
    cacheRaw = null;
    cache = EMPTY;
    return cache;
  }
}

function write(ids: number[]): void {
  try {
    localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify(ids));
  } catch {
    /* выбор не переживёт визит — не повод ломать клик */
  }
  cacheRaw = null; // следующий read перечитает
  listeners.forEach((listener) => listener());
}

export function subscribeGuestWishlist(callback: () => void): () => void {
  listeners.add(callback);
  // storage — тот же сайт в соседней вкладке: сохранили товар там, сердечко
  // должно закраситься и здесь.
  const onStorage = (event: StorageEvent) => {
    if (event.key === WISHLIST_STORAGE_KEY || event.key === null) {
      cacheRaw = null;
      callback();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", onStorage);
  };
}

/** Добавить/убрать товар. false — упёрлись в лимит (товар не добавлен). */
export function toggleGuestWishlist(productId: number): boolean {
  const current = readGuestWishlist();
  if (current.includes(productId)) {
    write(current.filter((id) => id !== productId));
    return true;
  }
  if (current.length >= WISHLIST_GUEST_LIMIT) return false;
  write([...current, productId]);
  return true;
}

/** Очистить гостевой список — после переноса в аккаунт. */
export function clearGuestWishlist(): void {
  write([]);
}
