// API-клиент заказов.

export type OrderItem = {
  id: number;
  product_id: number;
  code_1c: string;
  article: string;
  name: string;
  unit: string;
  price_base: string | null;
  price_final: string | null;
  discount: string | null;
  price_type: string;
  currency: string;
  quantity: number;
  line_total: string | null;
};

export type Order = {
  id: number;
  order_number: string;
  external_order_id: string;
  fulfillment_status: string;
  payment_status: string;
  sync_1c_status: string;
  display_status: string;
  customer_name: string;
  customer_phone: string;
  customer_email: string;
  customer_type: string;
  company_name: string;
  inn: string;
  kpp: string;
  legal_address: string;
  delivery_method: string;
  delivery_address: string;
  comment: string;
  payment_method: string;
  total: string;
  currency: string;
  created_at: string;
  items: OrderItem[];
};

export type PlaceOrderData = {
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  customer_type?: string;
  company_name?: string;
  inn?: string;
  kpp?: string;
  legal_address?: string;
  delivery_method: string;
  delivery_address?: string;
  comment?: string;
  payment_method: string;
};

const API_BASE = "/api";

/** Оформить заказ (POST /api/orders/). Возвращает созданный заказ. */
export async function placeOrder(data: PlaceOrderData): Promise<Order> {
  const res = await fetch(`${API_BASE}/orders/`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      (body as Record<string, string>).detail ?? `Order API ${res.status}`,
    );
  }
  return res.json() as Promise<Order>;
}

/** Получить заказ по ID (SSR, серверный вызов). */
export async function getOrder(
  id: string,
  base: string,
): Promise<Order | null> {
  const root = base.replace(/\/$/, "");
  const res = await fetch(`${root}/api/orders/${id}/`, {
    cache: "no-store",
    headers: { "X-Forwarded-Proto": "https" },
  });
  if (res.status === 404) return null;
  if (!res.ok) return null;
  return res.json() as Promise<Order>;
}
