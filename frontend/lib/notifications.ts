// Обёртки MAX-уведомлений к same-origin BFF (#519). Пути — без хвостового слэша
// (см. lib/cart.ts): trailingSlash:false у Next иначе 308-редиректит.
import { apiFetch } from "./api";
import type {
  AvailabilitySubscriptionStatus,
  NotificationItem,
  NotificationPreferences,
  NotificationPreferencesPatch,
  PaginatedNotifications,
} from "./types";

/** Текущие настройки уведомлений (GET → Django .../preferences/). */
export function getNotificationPreferences(): Promise<NotificationPreferences> {
  return apiFetch<NotificationPreferences>("/api/account/notifications/preferences");
}

/** Частичное обновление (PATCH → Django .../preferences/). */
export function updateNotificationPreferences(
  patch: NotificationPreferencesPatch,
): Promise<NotificationPreferences> {
  return apiFetch<NotificationPreferences>("/api/account/notifications/preferences", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

/** Статус подписки на товар (GET → Django availability-subscription/). */
export function getAvailabilitySubscriptionStatus(
  slug: string,
): Promise<AvailabilitySubscriptionStatus> {
  return apiFetch<AvailabilitySubscriptionStatus>(
    `/api/catalog/products/${encodeURIComponent(slug)}/availability-subscription`,
  );
}

/** Подписаться (POST, идемпотентно — повтор возвращает existing active). */
export function subscribeAvailability(slug: string): Promise<AvailabilitySubscriptionStatus> {
  return apiFetch<AvailabilitySubscriptionStatus>(
    `/api/catalog/products/${encodeURIComponent(slug)}/availability-subscription`,
    { method: "POST" },
  );
}

/** Отписаться (DELETE, идемпотентно). */
export function unsubscribeAvailability(slug: string): Promise<void> {
  return apiFetch<void>(
    `/api/catalog/products/${encodeURIComponent(slug)}/availability-subscription`,
    { method: "DELETE" },
  );
}

// --- Центр уведомлений (#515, страница — #513 epic) ---

/** Страница истории (DRF LimitOffsetPagination — offset/limit query-параметры). */
export function getNotificationHistory(offset = 0, limit = 20): Promise<PaginatedNotifications> {
  return apiFetch<PaginatedNotifications>(
    `/api/account/notifications?limit=${limit}&offset=${offset}`,
  );
}

export function markNotificationRead(id: number): Promise<NotificationItem> {
  return apiFetch<NotificationItem>(`/api/account/notifications/${id}/read`, { method: "POST" });
}

export function markAllNotificationsRead(): Promise<{ marked: number }> {
  return apiFetch<{ marked: number }>("/api/account/notifications/read-all", { method: "POST" });
}
