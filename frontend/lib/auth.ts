// API клиент аутентификации (#330, #434/M-11).
//
// Все вызовы идут через same-origin BFF (/api/account/**, /api/orders/), а не
// напрямую в Django. BFF (lib/bff.ts) добавляет самосогласованный CSRF
// (cookie + X-CSRFToken) для мутаций аутентифицированного пользователя — без
// этого logout/PATCH получали бы 403. Единый apiFetch даёт единообразную
// обработку ошибок (ApiError с detail из Django).
import { ApiError, apiFetch } from "@/lib/api";

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

export async function getMe() {
  try {
    return await apiFetch<Record<string, unknown>>("/api/account/me/", { method: "GET" });
  } catch (e) {
    if (e instanceof ApiError) return null;
    throw e;
  }
}

export async function otpLogin(phone: string, otp: string) {
  return apiFetch<Record<string, unknown>>("/api/account/otp-login/", {
    method: "POST",
    body: JSON.stringify({ phone, otp }),
  });
}

export async function getOrders() {
  // #438 (m-05): /api/orders/ теперь пагинирован ({count, results}); разворачиваем
  // results. Массив на входе тоже поддерживаем (обратная совместимость).
  try {
    const data = await apiFetch<{ results?: Record<string, unknown>[] } | Record<string, unknown>[]>(
      "/api/orders/",
      { method: "GET" },
    );
    return Array.isArray(data) ? data : (data.results ?? []);
  } catch (e) {
    if (e instanceof ApiError) return [];
    throw e;
  }
}

export async function getWishlist() {
  try {
    return await apiFetch<Record<string, unknown>[]>("/api/account/wishlist/", { method: "GET" });
  } catch (e) {
    if (e instanceof ApiError) return [];
    throw e;
  }
}
