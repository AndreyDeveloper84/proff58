// API клиент аутентификации (#330, #434/M-11).
//
// Все вызовы идут через same-origin BFF (/api/account/**, /api/orders/), а не
// напрямую в Django. BFF (lib/bff.ts) добавляет самосогласованный CSRF
// (cookie + X-CSRFToken) для мутаций аутентифицированного пользователя — без
// этого logout/PATCH получали бы 403. Единый apiFetch даёт единообразную
// обработку ошибок (ApiError с detail из Django).
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
  profile?: Partial<AccountProfile>;
};

export type WishlistItem = {
  product_id: number;
  product_name: string;
  product_slug: string;
};

export async function login(phone: string, password: string) {
  return apiFetch<Record<string, unknown>>("/api/account/login/", {
    method: "POST",
    body: JSON.stringify({ phone, password }),
  });
}

export async function register(data: {
  phone: string;
  password: string;
  full_name?: string;
  email?: string;
}) {
  return apiFetch<Record<string, unknown>>("/api/account/register/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function logout() {
  // Ждём ответ (CSRF-защищённый POST) ДО редиректа — иначе 403 маскируется и
  // сессия остаётся активной.
  await apiFetch<void>("/api/account/logout/", { method: "POST" });
}

export async function getMe(): Promise<AccountUser | null> {
  try {
    return await apiFetch<AccountUser>("/api/account/me/", { method: "GET" });
  } catch (e) {
    if (e instanceof ApiError) return null;
    throw e;
  }
}

export async function updateMe(data: AccountUserPatch): Promise<AccountUser> {
  return apiFetch<AccountUser>("/api/account/me/", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function changePhone(newPhone: string, password: string): Promise<void> {
  await apiFetch("/api/account/change-phone/", {
    method: "POST",
    body: JSON.stringify({ new_phone: newPhone, password }),
  });
}

export async function deleteAccount(): Promise<void> {
  await apiFetch("/api/account/delete/", { method: "POST" });
}

export async function otpLogin(phone: string, otp: string) {
  return apiFetch<Record<string, unknown>>("/api/account/otp-login/", {
    method: "POST",
    body: JSON.stringify({ phone, otp }),
  });
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
  return apiFetch<MaxAttempt>("/api/auth/max/start/", { method: "POST" });
}

// Старт привязки MAX к текущему аккаунту (из ЛК).
export async function maxLinkStart() {
  return apiFetch<MaxAttempt>("/api/account/max/link/", { method: "POST" });
}

export async function maxStatus(attemptId: string) {
  return apiFetch<MaxAttemptStatus>(`/api/auth/max/${attemptId}/status/`, { method: "GET" });
}

export async function maxCancel(attemptId: string) {
  return apiFetch<MaxAttemptStatus>(`/api/auth/max/${attemptId}/cancel/`, { method: "POST" });
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
  return apiFetch<{ linked: boolean; removed: boolean }>("/api/account/max/unlink/", {
    method: "POST",
  });
}

export async function maxAccountStatus() {
  try {
    return await apiFetch<{ linked: boolean; max_user_id: number | null; linked_at: string | null }>(
      "/api/account/max/status/",
      { method: "GET" },
    );
  } catch (e) {
    if (e instanceof ApiError) return { linked: false, max_user_id: null, linked_at: null };
    throw e;
  }
}

export async function getOrders(): Promise<Order[]> {
  // #438 (m-05): /api/orders теперь пагинирован ({count, results}); разворачиваем
  // results. Массив на входе тоже поддерживаем (обратная совместимость).
  // Без хвостового слэша: nginx матчит BFF-роуты точными путями (location = /api/orders),
  // а путь со слэшем уходил в Django напрямую мимо BFF (см. правило в lib/cart.ts).
  try {
    const data = await apiFetch<{ results?: Order[] } | Order[]>(
      "/api/orders",
      { method: "GET" },
    );
    return Array.isArray(data) ? data : (data.results ?? []);
  } catch (e) {
    if (e instanceof ApiError) return [];
    throw e;
  }
}

export async function getOrder(orderNumber: string): Promise<Order> {
  return apiFetch<Order>(`/api/orders/${encodeURIComponent(orderNumber)}`, {
    method: "GET",
  });
}

export async function getWishlist(): Promise<WishlistItem[]> {
  try {
    return await apiFetch<WishlistItem[]>("/api/account/wishlist/", { method: "GET" });
  } catch (e) {
    if (e instanceof ApiError) return [];
    throw e;
  }
}

export async function addWishlistItem(productId: number): Promise<void> {
  await apiFetch("/api/account/wishlist", {
    method: "POST",
    body: JSON.stringify({ product_id: productId }),
  });
}

export async function removeWishlistItem(productId: number): Promise<void> {
  await apiFetch("/api/account/wishlist", {
    method: "DELETE",
    body: JSON.stringify({ product_id: productId }),
  });
}
