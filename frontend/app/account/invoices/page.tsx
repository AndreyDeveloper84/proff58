"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Clock3, Download, FileText } from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { getMe } from "@/lib/auth";
import { formatPrice } from "@/lib/format";
import { getInvoices, type B2BInvoice } from "@/lib/invoices";
import { cn } from "@/lib/utils";

// Статусы счёта — машиночитаемые (union в lib/invoices.ts), без разбора текста.
const STATUS_BADGE: Record<B2BInvoice["status"], string> = {
  issued: "bg-blue-50 text-blue-700",
  paid: "bg-accent/10 text-accent",
  expired: "bg-red-50 text-danger",
  cancelled: "bg-raised text-ink-2",
};

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function InvoiceCard({ invoice }: { invoice: B2BInvoice }) {
  // Срок вышел, а janitor ещё не перевёл статус (интервал 10 мин) — честно
  // показываем «Истёк», скачивать уже нечего.
  const effectivelyExpired = invoice.is_expired && invoice.status === "issued";
  const badgeClass = effectivelyExpired ? STATUS_BADGE.expired : STATUS_BADGE[invoice.status];
  const badgeText = effectivelyExpired ? "Истёк" : invoice.status_display;
  const active = invoice.status === "issued" && !invoice.is_expired;

  return (
    <article className="rounded-lg border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-lg font-semibold text-ink">{invoice.number}</h3>
        <span className={cn("rounded-full px-3 py-1 text-xs font-semibold", badgeClass)}>
          {badgeText}
        </span>
      </div>

      <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <div className="flex justify-between gap-2 sm:block">
          <dt className="text-ink-3">Заказ</dt>
          <dd className="text-ink">
            <Link href="/account/orders" className="underline-offset-2 hover:underline">
              {invoice.order_number}
            </Link>{" "}
            <span className="text-ink-3">— {invoice.order_display_status}</span>
          </dd>
        </div>
        <div className="flex justify-between gap-2 sm:block">
          <dt className="text-ink-3">Сумма (товары)</dt>
          <dd className="font-display font-semibold text-ink">
            {formatPrice(Number(invoice.total))}
          </dd>
        </div>
        <div className="flex justify-between gap-2 sm:block">
          <dt className="text-ink-3">В т.ч. НДС {invoice.vat_rate}%</dt>
          <dd className="text-ink">{formatPrice(Number(invoice.vat_amount))}</dd>
        </div>
        <div className="flex justify-between gap-2 sm:block">
          <dt className="text-ink-3">Дата выставления</dt>
          <dd className="text-ink">{formatDateTime(invoice.issued_at)}</dd>
        </div>
      </dl>

      {active && (
        <p className="mt-3 flex items-center gap-1.5 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-700">
          <Clock3 className="h-4 w-4 shrink-0" aria-hidden />
          Счёт действителен до {formatDateTime(invoice.valid_until)} — до этого момента товар
          зарезервирован за вами.
        </p>
      )}
      {(invoice.status === "expired" || effectivelyExpired) && (
        <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          Срок действия счёта истёк {formatDateTime(invoice.valid_until)}: заказ отменён, резерв
          товара снят. Оформите заказ заново, если он ещё актуален.
        </p>
      )}

      {active && (
        <div className="mt-4">
          <a
            href={invoice.invoice_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90"
          >
            <Download className="h-4 w-4" aria-hidden />
            Открыть счёт
          </a>
        </div>
      )}
    </article>
  );
}

export default function InvoicesPage() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<B2BInvoice[]>([]);
  const [isB2B, setIsB2B] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getMe()
      .then(async (user) => {
        if (!user) {
          router.push("/account/login");
          return;
        }
        const data = await getInvoices();
        if (!active) return;
        setIsB2B(user.customer_type === "b2b");
        setInvoices(data);
        setLoading(false);
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (loading) {
    return (
      <AccountShell title="Счета">
        <div className="space-y-4" aria-label="Загрузка счетов">
          <div className="h-40 animate-pulse rounded-lg border border-line bg-surface" />
          <div className="h-40 animate-pulse rounded-lg border border-line bg-surface" />
        </div>
      </AccountShell>
    );
  }

  return (
    <AccountShell title="Счета">
      {invoices.length === 0 ? (
        <div className="rounded-lg border border-line bg-surface p-10 text-center">
          <FileText className="mx-auto h-10 w-10 text-ink-3" aria-hidden />
          <h2 className="mt-3 font-display text-lg font-semibold text-ink">Счетов пока нет</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-ink-2">
            {isB2B
              ? "Оформите заказ от организации — счёт появится здесь. Счёт действует 24 часа, на это время товар резервируется."
              : "Счета выставляются заказам организаций (B2B). Укажите тип покупателя «Организация» при оформлении заказа."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-ink-2">
            Счёт действует 24 часа с момента оформления заказа — на это время товар зарезервирован.
            Неоплаченный счёт истекает, заказ отменяется автоматически.
          </p>
          {invoices.map((invoice) => (
            <InvoiceCard key={invoice.number} invoice={invoice} />
          ))}
        </div>
      )}
    </AccountShell>
  );
}
