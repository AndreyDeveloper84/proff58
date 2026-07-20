// Клиент зон доставки (#54): GET /api/delivery/zones через same-origin BFF.
// Чекаут выбирает зону из этого списка и шлёт её слаг в POST /api/orders —
// сервер (quote_for_order) считает стоимость сам, cost здесь только для показа.
import { ApiError, apiFetch } from "@/lib/api";

export type DeliveryZoneOption = {
  zone: string; // slug — уходит в PlaceOrderData.delivery_zone
  name: string;
  type: "courier" | "pickup";
  cost: string; // Decimal → строка (для показа; сервер пересчитает сам)
  free_delivery: boolean;
};

export async function getDeliveryZones(cartTotal: number): Promise<DeliveryZoneOption[]> {
  try {
    const data = await apiFetch<{ zones: DeliveryZoneOption[] }>(
      `/api/delivery/zones?cart_total=${encodeURIComponent(cartTotal)}`,
      { method: "GET" },
    );
    return data.zones ?? [];
  } catch (e) {
    // Зоны — вспомогательные данные: их недоступность не должна ронять чекаут
    // (заказ без зоны создаётся как not_required — как и до этой фичи).
    if (e instanceof ApiError) return [];
    throw e;
  }
}
