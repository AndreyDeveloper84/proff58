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

// #569: слот доставки — дата + интервал. id уходит в PlaceOrderData.delivery_slot_id;
// сервер авторитетно перепроверит слот при оформлении.
export type DeliverySlotOption = {
  id: number;
  date: string; // ISO YYYY-MM-DD
  starts_at: string; // "10:00"
  ends_at: string; // "14:00"
};

export async function getDeliverySlots(zoneSlug?: string): Promise<DeliverySlotOption[]> {
  try {
    const qs = zoneSlug ? `?zone=${encodeURIComponent(zoneSlug)}` : "";
    const data = await apiFetch<{ slots: DeliverySlotOption[] }>(`/api/delivery/slots${qs}`, {
      method: "GET",
    });
    return data.slots ?? [];
  } catch (e) {
    // Пустой список = «слотов нет»: чекаут скрывает пикер и оформляет заказ
    // без слота (менеджер согласует время) — недоступность API не роняет заказ.
    if (e instanceof ApiError) return [];
    throw e;
  }
}
