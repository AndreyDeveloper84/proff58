// Счета B2B в ЛК (#560, эпик #557). Same-origin BFF → Django
// GET /api/account/invoices/ (owner-only, пагинирован как /api/orders/).
import { ApiError, apiFetch } from "@/lib/api";

export type B2BInvoice = {
  number: string;
  status: "issued" | "paid" | "expired" | "cancelled";
  status_display: string;
  order_number: string;
  order_display_status: string;
  fulfillment_status: string;
  payment_status: string;
  goods_total: string;
  vat_rate: number;
  vat_amount: string;
  amount_without_vat: string;
  total: string;
  currency: string;
  issued_at: string;
  valid_until: string;
  // Срок вышел (в т.ч. если janitor ещё не перевёл статус в expired).
  is_expired: boolean;
  // Ссылка на HTML-счёт (открывать в новой вкладке; owner-only на бэке).
  invoice_url: string;
};

/** #574: "error" вместо [] — сбой загрузки не выдаём за «счетов пока нет». */
export async function getInvoices(): Promise<B2BInvoice[] | "error"> {
  try {
    const data = await apiFetch<{ results?: B2BInvoice[] }>("/api/account/invoices", {
      method: "GET",
    });
    return data.results ?? [];
  } catch (e) {
    if (e instanceof ApiError) return "error";
    throw e;
  }
}
