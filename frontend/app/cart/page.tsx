"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  Heart,
  LockKeyhole,
  MapPin,
  ShieldCheck,
  ShoppingCart,
  Trash2,
  Truck,
} from "lucide-react";
import { CartItemRow } from "@/components/cart/CartItemRow";
import { useCart } from "@/components/cart/CartProvider";
import { PromoCodeField } from "@/components/cart/PromoCodeField";
import { MobileBottomNav } from "@/components/layout/MobileBottomNav";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { addWishlistItem } from "@/lib/auth";
import { formatPrice, pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

const RECOMMENDATIONS = [
  { name: "Аккумуляторы для инструмента", query: "аккумулятор" },
  { name: "Наборы бит и оснастка", query: "набор бит" },
  { name: "Рабочие перчатки", query: "перчатки" },
  { name: "Смазка для редуктора", query: "смазка" },
  { name: "Защитные очки", query: "защитные очки" },
] as const;

type DeliveryMethod = "delivery" | "pickup";

export default function CartPage() {
  const { cart, loading, total, update, remove } = useCart();
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deliveryMethod, setDeliveryMethod] = useState<DeliveryMethod>("delivery");
  const selectionInitialized = useRef(false);

  useEffect(() => {
    const lineIds = cart?.lines.map((line) => line.id) ?? [];
    setSelectedIds((current) => {
      if (!selectionInitialized.current && lineIds.length > 0) {
        selectionInitialized.current = true;
        return new Set(lineIds);
      }
      const existing = new Set(lineIds);
      return new Set([...current].filter((id) => existing.has(id)));
    });
  }, [cart]);

  const run = useCallback(async (action: () => Promise<unknown>) => {
    setMutating(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось обновить корзину");
    } finally {
      setMutating(false);
    }
  }, []);

  const handleUpdate = useCallback(
    (itemId: number, qty: number) => run(() => update(itemId, qty)),
    [run, update],
  );
  const handleRemove = useCallback(
    (itemId: number) => run(() => remove(itemId)),
    [run, remove],
  );

  const handleSelect = useCallback((itemId: number, selected: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (selected) next.add(itemId);
      else next.delete(itemId);
      return next;
    });
  }, []);

  const allSelected = Boolean(
    cart?.lines.length && selectedIds.size === cart.lines.length,
  );

  const handleSelectAll = useCallback(
    (selected: boolean) => {
      setSelectedIds(
        selected ? new Set(cart?.lines.map((line) => line.id) ?? []) : new Set(),
      );
    },
    [cart],
  );

  const selectedLines = useMemo(
    () => cart?.lines.filter((line) => selectedIds.has(line.id)) ?? [],
    [cart, selectedIds],
  );

  const baseTotal = useMemo(
    () =>
      (cart?.lines ?? []).reduce((sum, line) => {
        const unit = Number(line.price_base ?? line.price_final) || 0;
        return sum + unit * line.quantity;
      }, 0),
    [cart],
  );
  const discount = Math.max(0, baseTotal - total);
  // #571: серверный промо-breakdown (grand_total — к оплате после скидок по акциям).
  const promoDiscount = Number(cart?.items_discount_total ?? 0) || 0;
  const payable = cart ? Number(cart.grand_total) || total : total;

  const handleRemoveSelected = () =>
    run(async () => {
      for (const line of selectedLines) await remove(line.id);
      setNotice("Выбранные товары удалены");
    });

  const handleMoveToWishlist = () =>
    run(async () => {
      for (const line of selectedLines) await addWishlistItem(line.product_id);
      for (const line of selectedLines) await remove(line.id);
      setNotice("Товары перенесены в избранное");
    });

  if (loading) {
    return (
      <main className="mx-auto min-h-[60vh] w-full max-w-[1480px] px-4 py-10 sm:px-6 lg:px-8">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="h-96 animate-pulse rounded-lg border border-line bg-surface" />
          <div className="h-80 animate-pulse rounded-lg border border-line bg-surface" />
        </div>
      </main>
    );
  }

  const isEmpty = !cart || cart.lines.length === 0;
  // #375: при смешении валют бэк обнуляет total и поднимает флаг — оформление
  // невозможно, показываем причину вместо загадочного «Итого: 0 ₽».
  const mixedCurrencies = Boolean(cart?.has_mixed_currencies);
  // #574: суммы — в валюте корзины, как в кабинете (раньше всегда «₽»).
  const currency = cart?.currency || "RUB";
  const lineCount = cart?.lines.length ?? 0;

  return (
    <main className="mx-auto w-full max-w-[1480px] px-4 pb-44 pt-5 sm:px-6 lg:px-8 lg:pb-10 lg:pt-7">
      <nav
        aria-label="Хлебные крошки"
        className="mb-4 hidden items-center gap-2 text-xs text-ink-3 sm:flex"
      >
        <Link href="/" className="hover:text-accent">
          Главная
        </Link>
        <span aria-hidden>›</span>
        <span>Корзина</span>
      </nav>

      <div className="mb-5 flex items-center gap-3">
        <h1 className="font-display text-3xl font-semibold text-ink">Корзина</h1>
        {!isEmpty && (
          <span className="rounded-full bg-raised px-2.5 py-1 text-xs font-medium text-ink-2">
            {lineCount} {pluralize(lineCount, "товар", "товара", "товаров")}
          </span>
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {error}
        </div>
      )}
      {notice && (
        <div
          role="status"
          className="mb-4 rounded-lg border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-accent"
        >
          {notice}
        </div>
      )}

      {isEmpty ? (
        <section className="flex min-h-80 flex-col items-center justify-center gap-4 rounded-lg border border-line bg-surface p-8 text-center">
          <div className="grid h-20 w-20 place-items-center rounded-full bg-raised">
            <ShoppingCart className="h-10 w-10 text-ink-3" strokeWidth={1.5} aria-hidden />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-ink">Корзина пуста</h2>
            <p className="mt-1 text-sm text-ink-3">
              Перейдите в каталог, чтобы добавить товары
            </p>
          </div>
          <Link href="/catalog">
            <Button variant="accent">Перейти в каталог</Button>
          </Link>
        </section>
      ) : (
        <>
          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
            <section className="min-w-0">
              <div className="flex min-h-12 flex-wrap items-center gap-2 border-b border-line px-1 pb-2 sm:gap-4">
                <label className="inline-flex min-h-10 items-center gap-2 text-sm font-medium text-ink-2">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    disabled={mutating}
                    onChange={(event) => handleSelectAll(event.target.checked)}
                    className="h-4 w-4 rounded border-line accent-accent"
                  />
                  Выбрать все
                </label>

                <button
                  type="button"
                  disabled={mutating || selectedLines.length === 0}
                  onClick={handleRemoveSelected}
                  className="ml-auto inline-flex min-h-10 items-center gap-2 rounded-md px-2 text-xs font-medium text-ink-3 transition hover:bg-raised hover:text-danger disabled:opacity-40 sm:text-sm"
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                  <span className="hidden sm:inline">Удалить выбранные</span>
                </button>
                <button
                  type="button"
                  disabled={mutating || selectedLines.length === 0}
                  onClick={handleMoveToWishlist}
                  className="inline-flex min-h-10 items-center gap-2 rounded-md px-2 text-xs font-medium text-ink-3 transition hover:bg-raised hover:text-accent disabled:opacity-40 sm:text-sm"
                >
                  <Heart className="h-4 w-4" aria-hidden />
                  <span className="hidden sm:inline">Перенести в избранное</span>
                </button>
              </div>

              <div className="overflow-hidden rounded-lg border border-line bg-surface">
                {cart.lines.map((line) => (
                  <CartItemRow
                    key={line.id}
                    line={line}
                    selected={selectedIds.has(line.id)}
                    onSelect={handleSelect}
                    onUpdate={handleUpdate}
                    onRemove={handleRemove}
                    disabled={mutating}
                  />
                ))}
              </div>

              <Link
                href="/catalog"
                className="mt-4 inline-flex min-h-10 items-center gap-2 text-sm font-medium text-ink-2 transition hover:text-accent"
              >
                <ChevronLeft className="h-4 w-4" aria-hidden />
                Продолжить покупки
              </Link>
            </section>

            <aside className="space-y-4 lg:sticky lg:top-24">
              <section className="rounded-lg border border-line bg-surface p-4">
                <h2 className="text-sm font-semibold text-ink">Способ получения</h2>
                <div className="mt-3 space-y-2">
                  <DeliveryOption
                    checked={deliveryMethod === "delivery"}
                    onChange={() => setDeliveryMethod("delivery")}
                    icon={Truck}
                    title="Доставка"
                    description="По Пензе и области"
                    hint="Рассчитаем на следующем шаге"
                  />
                  <DeliveryOption
                    checked={deliveryMethod === "pickup"}
                    onChange={() => setDeliveryMethod("pickup")}
                    icon={MapPin}
                    title="Самовывоз"
                    description="ул. Суворова, 225"
                    hint="Бесплатно"
                  />
                </div>
              </section>

              <section className="rounded-lg border border-line bg-surface p-4">
                <PromoCodeField />
                <div className="mt-3 space-y-3 text-sm">
                  <SummaryRow label={`${lineCount} ${pluralize(lineCount, "товар", "товара", "товаров")}`} value={formatPrice(baseTotal, currency)} />
                  <SummaryRow
                    label="Скидка"
                    value={discount > 0 ? `− ${formatPrice(discount, currency)}` : formatPrice(0, currency)}
                    accent={discount > 0}
                  />
                  {promoDiscount > 0 && (
                    <SummaryRow
                      label="Скидка по акциям"
                      value={`− ${formatPrice(promoDiscount, currency)}`}
                      accent
                    />
                  )}
                </div>
                <div className="my-4 border-t border-line" />
                <div className="flex items-end justify-between gap-3">
                  <span className="text-base font-semibold text-ink">Итого</span>
                  <span className="font-display text-3xl font-bold text-ink">
                    {mixedCurrencies ? "—" : formatPrice(payable, currency)}
                  </span>
                </div>
                {mixedCurrencies && (
                  <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                    В корзине товары в разных валютах — итог не считается. Оформите их
                    отдельными заказами, удалив лишние позиции.
                  </p>
                )}
                {mixedCurrencies ? (
                  <span className="mt-5 flex h-12 w-full cursor-not-allowed items-center justify-center rounded-md bg-accent/40 px-5 text-sm font-semibold text-accent-ink">
                    Перейти к оформлению
                  </span>
                ) : (
                  <Link
                    href="/checkout"
                    className="mt-5 flex h-12 w-full items-center justify-center rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink transition hover:brightness-95"
                  >
                    Перейти к оформлению
                  </Link>
                )}
                <div className="mt-4 flex items-center gap-2 text-xs text-accent">
                  <LockKeyhole className="h-4 w-4" aria-hidden />
                  <div>
                    <p className="font-semibold">Безопасная оплата</p>
                    <p className="mt-0.5 text-[10px] font-normal text-ink-3">
                      Ваши данные защищены
                    </p>
                  </div>
                </div>
              </section>
            </aside>
          </div>

          <Recommendations />

          <div className="fixed inset-x-0 bottom-[68px] z-40 flex h-[72px] items-center justify-between gap-3 border-t border-line bg-surface px-4 shadow-[0_-8px_24px_rgba(20,24,27,0.08)] lg:hidden">
            <div>
              <p className="text-[11px] text-ink-3">Итого:</p>
              <p className="text-lg font-bold text-ink">
                {mixedCurrencies ? "—" : formatPrice(payable, currency)}
              </p>
            </div>
            {mixedCurrencies ? (
              <span className="flex h-11 cursor-not-allowed items-center justify-center rounded-md bg-accent/40 px-5 text-sm font-semibold text-accent-ink">
                К оформлению
              </span>
            ) : (
              <Link
                href="/checkout"
                className="flex h-11 items-center justify-center rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink"
              >
                К оформлению
              </Link>
            )}
          </div>
        </>
      )}

      <MobileBottomNav active="cart" />
    </main>
  );
}

function DeliveryOption({
  checked,
  onChange,
  icon: Icon,
  title,
  description,
  hint,
}: {
  checked: boolean;
  onChange: () => void;
  icon: typeof Truck;
  title: string;
  description: string;
  hint: string;
}) {
  return (
    <label
      className={cn(
        "grid cursor-pointer grid-cols-[20px_minmax(0,1fr)_24px] gap-2 rounded-md border p-3 transition",
        checked ? "border-accent bg-accent/5" : "border-line hover:bg-raised",
      )}
    >
      <input
        type="radio"
        name="delivery-method"
        checked={checked}
        onChange={onChange}
        className="mt-0.5 h-4 w-4 accent-accent"
      />
      <span>
        <span className="block text-xs font-semibold text-ink">{title}</span>
        <span className="mt-1 block text-[10px] leading-4 text-ink-3">{description}</span>
        <span className="block text-[10px] leading-4 text-ink-3">{hint}</span>
      </span>
      <Icon className="h-5 w-5 text-ink-2" aria-hidden />
    </label>
  );
}

function SummaryRow({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-2">{label}</span>
      <span className={cn("font-semibold", accent ? "text-accent" : "text-ink")}>
        {value}
      </span>
    </div>
  );
}

function Recommendations() {
  return (
    <section className="mt-8">
      <h2 className="text-base font-semibold text-ink">С этим товаром покупают</h2>
      <div className="mt-4 flex snap-x gap-3 overflow-x-auto pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {RECOMMENDATIONS.map((item) => (
          <Link
            key={item.query}
            href={`/search?q=${encodeURIComponent(item.query)}`}
            className="group w-[180px] shrink-0 snap-start overflow-hidden rounded-lg border border-line bg-surface p-3 transition hover:-translate-y-0.5 hover:shadow-md sm:w-[210px]"
          >
            <div className="relative grid h-28 place-items-center rounded-md bg-photo">
              <Image
                src="/sample-tool.svg"
                alt=""
                width={100}
                height={100}
                className="h-24 w-24 object-contain transition group-hover:scale-105"
              />
              <ShieldCheck
                className="absolute right-2 top-2 h-4 w-4 text-ink-3"
                aria-hidden
              />
            </div>
            <p className="mt-3 line-clamp-2 text-sm font-semibold text-ink">{item.name}</p>
            <p className="mt-2 text-xs font-medium text-accent">Посмотреть товары</p>
          </Link>
        ))}
      </div>
    </section>
  );
}
