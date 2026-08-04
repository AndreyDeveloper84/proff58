// API клиент аутентификации (#330, #434/M-11).
//
// Все вызовы идут через same-origin BFF (/api/account/**, /api/orders/), а не
// напрямую в Django. BFF (lib/bff.ts) добавляет самосогласованный CSRF
// (cookie + X-CSRFToken) для мутаций аутентифицированного пользователя — без
// этого logout/PATCH получали бы 403. Единый apiFetch даёт единообразную
// обработку ошибок (ApiError с detail из Django).
//
// Пути — БЕЗ хвостового слэша. Next отдаёт на такой адрес 308 на версию без
// слэша, то есть каждый вызов уходил дважды: и вход, и /me на каждой странице
// кабинета, и опрос статуса MAX в цикле. Слэш нужен только внутри BFF, когда
// route handler зовёт Django (его APPEND_SLASH ждёт именно такой путь).
import { ApiError, apiFetch } from "@/lib/api";
import type { Order } from "@/lib/types";

export type AccountProfile = {
  company_name: string;
  inn: string;
  kpp: string;
  legal_address: string;
};

export type AccountUser = {
  id: number;
  phone: string;
  email: string;
  full_name: string;
  customer_type: "b2c" | "b2b";
  profile: AccountProfile | null;
};

export type AccountUserPatch = {
  full_name?: string;
  email?: string;
  // Переход «частное лицо ↔ организация» прямо из кабинета: тот, кто
  // зарегистрировался физлицом, начинает покупать от компании. Переход в
  // организацию сервер примет только вместе с реквизитами.
  customer_type?: "b2c" | "b2b";
  profile?: Partial<AccountProfile>;
};

export type WishlistItem = {
  product_id: number;
  product_name: string;
  product_slug: string;
};

// Вход — по e-mail. Телефон логином не является: он контакт заказа и
// идентификатор для MAX (см. apps/accounts/models.py).
export async function login(email: string, password: string) {
  return apiFetch<Record<string, unknown>>("/api/account/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(data: {
  email: string;
  password: string;
  full_name?: string;
  // Организация указывает реквизиты сразу — без них кабинет юрлица пуст,
  // а счёт запросить не из чего.
  customer_type?: "b2c" | "b2b";
  company_name?: string;
  inn?: string;
  kpp?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/account/register", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function logout() {
  // Ждём ответ (CSRF-защищённый POST) ДО редиректа — иначе 403 маскируется и
  // сессия остаётся активной.
  await apiFetch<void>("/api/account/logout", { method: "POST" });
}

/**
 * Профиль текущего пользователя; null — не вошёл (401/403).
 *
 * Любая другая беда (сервер отдал 500, лимит запросов, обрыв связи) — это НЕ
 * «пользователь не вошёл»: раньше здесь возвращался null на любую ошибку, и
 * кабинет выкидывал на форму входа человека с живой сессией, стоило сети моргнуть.
 * Такие случаи пробрасываются вызывающему — см. {@link checkAuth}.
 */
export async function getMe(): Promise<AccountUser | null> {
  try {
    return await apiFetch<AccountUser>("/api/account/me", { method: "GET" });
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
    throw e;
  }
}

/** Итог проверки доступа в кабинет: сам пользователь, гость или сбой связи/сервера. */
export type AuthCheck = AccountUser | "anonymous" | "error";

/**
 * Проверка доступа для страниц кабинета. Три исхода вместо двух: гостя уводим на
 * вход, а при сбое показываем «сервис недоступен» — выгонять из кабинета за чужую
 * ошибку нельзя, сессия-то цела.
 */
export async function checkAuth(): Promise<AuthCheck> {
  try {
    return (await getMe()) ?? "anonymous";
  } catch {
    return "error";
  }
}

// loginHref переехал в lib/auth-state (модуль без зависимостей — его импортирует
// и proxy.ts). Реэкспорт оставлен, чтобы не переписывать импорты по всему фронту.
export { loginHref } from "@/lib/auth-state";

export async function updateMe(data: AccountUserPatch): Promise<AccountUser> {
  return apiFetch<AccountUser>("/api/account/me", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function changePhone(newPhone: string, password: string): Promise<void> {
  await apiFetch("/api/account/change-phone", {
    method: "POST",
    body: JSON.stringify({ new_phone: newPhone, password }),
  });
}

export async function deleteAccount(): Promise<void> {
  await apiFetch("/api/account/delete", { method: "POST" });
}

// --- Авторизация через MAX (deeplink + one-time attempt, #492) ---

export type MaxAttempt = {
  attempt_id: string;
  deeplink: string;
  expires_at: string;
  status: string;
};

export type MaxAttemptStatus = { status: string; failure_reason: string | null };

// Старт попытки входа/регистрации через MAX.
export async function maxStart() {
  return apiFetch<MaxAttempt>("/api/auth/max/start", { method: "POST" });
}

// Старт привязки MAX к текущему аккаунту (из ЛК).
export async function maxLinkStart() {
  return apiFetch<MaxAttempt>("/api/account/max/link", { method: "POST" });
}

export async function maxStatus(attemptId: string) {
  return apiFetch<MaxAttemptStatus>(`/api/auth/max/${attemptId}/status`, { method: "GET" });
}

export async function maxCancel(attemptId: string) {
  return apiFetch<MaxAttemptStatus>(`/api/auth/max/${attemptId}/cancel`, { method: "POST" });
}

// --- Отслеживание гостевого заказа в MAX (#520) — свой start/status, тот же
// формат попытки (MaxAttempt/MaxAttemptStatus). cancel — общий maxCancel() выше
// (эндпоинт отмены общий для всех типов попыток). Статус НЕ логинит гостя —
// это не вход, только подписка конкретного заказа на уведомления.

export async function startOrderTracking(orderNumber: string, accessToken: string) {
  return apiFetch<MaxAttempt>(
    `/api/orders/${encodeURIComponent(orderNumber)}/max-track/start`,
    { method: "POST", body: JSON.stringify({ access_token: accessToken }) },
  );
}

export async function getOrderTrackingStatus(attemptId: string) {
  return apiFetch<MaxAttemptStatus>(`/api/orders/max-track/${attemptId}/status`, {
    method: "GET",
  });
}

export async function maxUnlink() {
  return apiFetch<{ linked: boolean; removed: boolean }>("/api/account/max/unlink", {
    method: "POST",
  });
}

export async function maxAccountStatus() {
  try {
    return await apiFetch<{ linked: boolean; max_user_id: number | null; linked_at: string | null }>(
      "/api/account/max/status",
      { method: "GET" },
    );
  } catch (e) {
    if (e instanceof ApiError) return { linked: false, max_user_id: null, linked_at: null };
    throw e;
  }
}

export async function getOrders(): Promise<Order[] | "error"> {
  // #438 (m-05): /api/orders теперь пагинирован ({count, results}); разворачиваем
  // results. Массив на входе тоже поддерживаем (обратная совместимость).
  // Без хвостового слэша: nginx матчит BFF-роуты точными путями (location = /api/orders),
  // а путь со слэшем уходил в Django напрямую мимо BFF (см. правило в lib/cart.ts).
  // #574: сбой возвращает "error", а не [] — иначе при 500 экран показывал
  // «Заказов пока нет», то есть пустое состояние врало о наличии данных.
  try {
    const data = await apiFetch<{ results?: Order[] } | Order[]>(
      "/api/orders",
      { method: "GET" },
    );
    return Array.isArray(data) ? data : (data.results ?? []);
  } catch (e) {
    if (e instanceof ApiError) return "error";
    throw e;
  }
}

export async function getOrder(orderNumber: string): Promise<Order> {
  return apiFetch<Order>(`/api/orders/${encodeURIComponent(orderNumber)}`, {
    method: "GET",
  });
}

/**
 * Избранное аккаунта.
 *
 * Три исхода, а не два: "error" (#574) отличает сбой загрузки от пустого списка,
 * а "unauthorized" — от них обоих. Без последнего посетитель с протухшей cookie
 * выглядел для интерфейса вошедшим: каждый клик уходил на сервер, получал 401 и
 * откатывался, то есть сердечко не реагировало вообще.
 */
export async function getWishlist(): Promise<WishlistItem[] | "error" | "unauthorized"> {
  try {
    return await apiFetch<WishlistItem[]>("/api/account/wishlist", { method: "GET" });
  } catch (e) {
    if (e instanceof ApiError) {
      return e.status === 401 || e.status === 403 ? "unauthorized" : "error";
    }
    throw e;
  }
}

export async function addWishlistItem(productId: number): Promise<void> {
  await apiFetch("/api/account/wishlist", {
    method: "POST",
    body: JSON.stringify({ product_id: productId }),
  });
}

/**
 * Перенести избранное гостя в аккаунт одним запросом.
 *
 * Списком, а не по товару: иначе вход у человека с двумя десятками сохранённых
 * позиций превращался бы в веер запросов ровно в тот момент, когда страница и
 * так грузится. Повторный перенос безопасен — сервер игнорирует дубли.
 */
export async function addWishlistItems(productIds: number[]): Promise<void> {
  if (productIds.length === 0) return;
  await apiFetch("/api/account/wishlist", {
    method: "POST",
    body: JSON.stringify({ product_ids: productIds }),
  });
}

export async function removeWishlistItem(productId: number): Promise<void> {
  await apiFetch("/api/account/wishlist", {
    method: "DELETE",
    body: JSON.stringify({ product_id: productId }),
  });
}
