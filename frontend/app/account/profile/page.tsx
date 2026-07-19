"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Building2,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  Clock3,
  Edit3,
  GitCompare,
  Heart,
  LogOut,
  MapPin,
  PackageCheck,
  UserRound,
} from "lucide-react";
import { AccountShell } from "@/components/account/AccountShell";
import { MaxLinkCard } from "@/components/account/MaxLinkCard";
import { NotificationPreferencesCard } from "@/components/account/NotificationPreferencesCard";
import {
  getMe,
  getOrders,
  getWishlist,
  logout,
  type AccountUser,
  type WishlistItem,
} from "@/lib/auth";
import { formatPrice, pluralize } from "@/lib/format";
import type { Order } from "@/lib/types";
import { cn } from "@/lib/utils";

function isOrderInProgress(order: Order) {
  const status = order.display_status.toLowerCase();
  return !["доставлен", "выполнен", "отмен", "возврат"].some((token) =>
    status.includes(token),
  );
}

function statusClass(status: string) {
  const value = status.toLowerCase();
  if (value.includes("достав") || value.includes("выполн")) {
    return "bg-accent/10 text-accent";
  }
  if (value.includes("обработ") || value.includes("сбор") || value.includes("подтверж")) {
    return "bg-blue-50 text-blue-700";
  }
  if (value.includes("отмен") || value.includes("возврат")) {
    return "bg-red-50 text-danger";
  }
  return "bg-raised text-ink-2";
}

function orderDate(value: string) {
  return new Date(value).toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function DashboardLoading() {
  return (
    <AccountShell title="Личный кабинет">
      <div className="space-y-5" aria-label="Загрузка личного кабинета">
        <div className="h-40 animate-pulse rounded-lg border border-line bg-surface" />
        <div className="h-72 animate-pulse rounded-lg border border-line bg-surface" />
        <div className="grid gap-4 md:grid-cols-3">
          <div className="h-40 animate-pulse rounded-lg border border-line bg-surface" />
          <div className="h-40 animate-pulse rounded-lg border border-line bg-surface" />
          <div className="h-40 animate-pulse rounded-lg border border-line bg-surface" />
        </div>
      </div>
    </AccountShell>
  );
}

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<AccountUser | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [wishlist, setWishlist] = useState<WishlistItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getMe()
      .then(async (data) => {
        if (!data) {
          router.push("/account/login");
          return;
        }
        const [orderData, wishlistData] = await Promise.all([getOrders(), getWishlist()]);
        if (!active) return;
        setUser(data);
        setOrders(orderData);
        setWishlist(wishlistData);
        setLoading(false);
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [router]);

  const orderSummary = useMemo(() => {
    const inProgress = orders.filter(isOrderInProgress).length;
    const total = orders.reduce((sum, order) => sum + (Number(order.total) || 0), 0);
    return { inProgress, total };
  }, [orders]);

  if (loading) return <DashboardLoading />;
  if (!user) return null;

  const displayName = user.full_name || "Покупатель";
  const company = user.profile?.company_name;
  const deliveryAddress =
    orders.find((order) => order.delivery_address)?.delivery_address ||
    user.profile?.legal_address ||
    "";

  return (
    <AccountShell title="Личный кабинет">
      <div className="space-y-5">
        <section className="overflow-hidden rounded-lg border border-line bg-surface">
          <div className="grid grid-cols-2 xl:grid-cols-[1.55fr_repeat(4,minmax(112px,1fr))]">
            <div className="col-span-2 border-b border-line p-5 xl:col-span-1 xl:border-b-0 xl:border-r">
              <div className="flex items-start gap-4">
                <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-raised xl:hidden">
                  <UserRound className="h-7 w-7 text-ink-2" aria-hidden />
                </div>
                <div className="min-w-0">
                  <h2 className="text-lg font-semibold text-ink">Добро пожаловать!</h2>
                  <p className="mt-2 truncate text-sm font-medium text-ink">{displayName}</p>
                  <p className="mt-0.5 truncate text-xs text-ink-3">
                    {company || (user.customer_type === "b2b" ? "Корпоративный клиент" : user.phone)}
                  </p>
                  <a
                    href="#personal-data"
                    className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-accent hover:underline"
                  >
                    <Edit3 className="h-3.5 w-3.5" aria-hidden />
                    Редактировать профиль
                  </a>
                </div>
              </div>
            </div>

            <SummaryStat
              icon={ClipboardList}
              value={String(orders.length)}
              label={pluralize(orders.length, "заказ", "заказа", "заказов")}
              rightBorder
              bottomBorder
            />
            <SummaryStat
              icon={Clock3}
              value={String(orderSummary.inProgress)}
              label="В обработке"
              bottomBorder
            />
            <SummaryStat
              icon={CircleDollarSign}
              value={formatPrice(orderSummary.total)}
              label="Сумма заказов"
              rightBorder
            />
            <SummaryStat
              icon={PackageCheck}
              value="0 ₽"
              label="Бонусный баланс"
              hint="скоро"
              last
            />
          </div>
        </section>

        <div className="grid items-stretch gap-5 xl:grid-cols-[minmax(0,1fr)_190px]">
          <section className="overflow-hidden rounded-lg border border-line bg-surface">
            <div className="flex items-center justify-between border-b border-line px-4 py-3.5">
              <h2 className="text-sm font-semibold text-ink">Мои заказы</h2>
              <Link
                href="/account/orders"
                className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline"
              >
                Все заказы
                <ChevronRight className="h-3.5 w-3.5" aria-hidden />
              </Link>
            </div>

            {orders.length === 0 ? (
              <div className="px-4 py-10 text-center">
                <ClipboardList className="mx-auto h-9 w-9 text-ink-3" aria-hidden />
                <p className="mt-3 text-sm font-semibold text-ink">Заказов пока нет</p>
                <p className="mt-1 text-xs text-ink-3">
                  Оформите первый заказ — он появится в этом разделе.
                </p>
                <Link
                  href="/catalog"
                  className="mt-4 inline-flex h-10 items-center rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink"
                >
                  Перейти в каталог
                </Link>
              </div>
            ) : (
              <div>
                {orders.slice(0, 4).map((order) => (
                  <div
                    key={order.id}
                    className="grid gap-2 border-b border-line px-4 py-3.5 last:border-b-0 sm:grid-cols-[1.2fr_1fr_0.8fr_auto] sm:items-center"
                  >
                    <div>
                      <p className="text-sm font-semibold text-ink">
                        № {order.order_number}
                      </p>
                      <p className="mt-0.5 text-[11px] text-ink-3">
                        от {orderDate(order.created_at)}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "w-fit rounded-md px-2 py-1 text-[11px] font-semibold",
                        statusClass(order.display_status),
                      )}
                    >
                      {order.display_status}
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-ink">
                        {formatPrice(Number(order.total) || 0, order.currency)}
                      </p>
                      <p className="mt-0.5 text-[11px] text-ink-3">
                        {order.items.length}{" "}
                        {pluralize(order.items.length, "товар", "товара", "товаров")}
                      </p>
                    </div>
                    <Link
                      href="/account/orders"
                      className="inline-flex h-9 items-center justify-center rounded-md border border-line px-3 text-xs font-semibold text-ink transition hover:bg-raised"
                    >
                      Подробнее
                    </Link>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="relative overflow-hidden rounded-lg border border-line bg-surface p-5">
            <p className="text-sm font-semibold text-ink">Бонусный баланс</p>
            <p className="mt-6 text-3xl font-bold text-accent">0 ₽</p>
            <p className="mt-2 text-xs text-ink-3">Программа лояльности скоро появится</p>
            <div
              className="pointer-events-none absolute -bottom-8 -right-6 grid h-28 w-28 place-items-center rounded-full border-8 border-raised text-5xl font-bold text-raised"
              aria-hidden
            >
              ₽
            </div>
          </section>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          <PreviewCard
            id="wishlist-preview"
            icon={Heart}
            title="Избранное"
            count={wishlist.length}
            href="/account/wishlist"
          >
            {wishlist.length > 0 ? (
              <div className="flex gap-3">
                {wishlist.slice(0, 3).map((item) => (
                  <Link
                    key={item.product_id}
                    href={`/product/${item.product_slug}`}
                    className="group min-w-0 flex-1"
                    title={item.product_name}
                  >
                    <div className="grid h-16 place-items-center rounded-md bg-photo">
                      <Image
                        src="/sample-tool.svg"
                        alt=""
                        width={56}
                        height={56}
                        className="h-12 w-12 object-contain transition group-hover:scale-105"
                      />
                    </div>
                    <p className="mt-1 truncate text-[11px] text-ink-2">{item.product_name}</p>
                  </Link>
                ))}
              </div>
            ) : (
              <EmptyPreview text="Добавляйте товары, чтобы не потерять их" />
            )}
          </PreviewCard>

          <PreviewCard
            id="comparison"
            icon={GitCompare}
            title="Сравнение"
            count={0}
            href="/catalog"
          >
            <EmptyPreview text="Выберите похожие товары в каталоге для сравнения" />
          </PreviewCard>

          <PreviewCard
            id="addresses"
            icon={MapPin}
            title="Адреса доставки"
            count={deliveryAddress ? 1 : 0}
            href="#personal-data"
          >
            {deliveryAddress ? (
              <div className="rounded-md bg-raised p-3">
                <p className="text-xs leading-5 text-ink-2">{deliveryAddress}</p>
              </div>
            ) : (
              <EmptyPreview text="Адрес появится после оформления заказа" />
            )}
          </PreviewCard>
        </div>

        <section
          id="personal-data"
          className="scroll-mt-24 rounded-lg border border-line bg-surface p-5 lg:p-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-ink">Личные данные</h2>
              <p className="mt-1 text-xs text-ink-3">
                Контактная информация и настройки аккаунта
              </p>
            </div>
            <button
              type="button"
              onClick={async () => {
                try {
                  await logout();
                } finally {
                  router.push("/");
                }
              }}
              className="inline-flex min-h-10 items-center gap-2 rounded-md px-3 text-sm font-medium text-danger transition hover:bg-red-50"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              Выйти
            </button>
          </div>

          <dl className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <ProfileField label="Имя" value={user.full_name || "Не указано"} />
            <ProfileField label="Телефон" value={user.phone} />
            <ProfileField label="Email" value={user.email || "Не указан"} />
            <ProfileField
              label="Тип покупателя"
              value={user.customer_type === "b2b" ? "Компания" : "Физическое лицо"}
            />
          </dl>

          {user.profile && (
            <div id="company-profile" className="mt-6 scroll-mt-24 border-t border-line pt-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Building2 className="h-4 w-4 text-accent" aria-hidden />
                Профиль компании
              </h3>
              <dl className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <ProfileField label="Организация" value={user.profile.company_name || "Не указана"} />
                <ProfileField label="ИНН" value={user.profile.inn || "Не указан"} />
                <ProfileField label="КПП" value={user.profile.kpp || "Не указан"} />
                <ProfileField
                  label="Юридический адрес"
                  value={user.profile.legal_address || "Не указан"}
                />
              </dl>
            </div>
          )}

          <div id="payment-methods" className="scroll-mt-24">
            <MaxLinkCard />
          </div>
          <NotificationPreferencesCard />
        </section>
      </div>
    </AccountShell>
  );
}

function SummaryStat({
  icon: Icon,
  value,
  label,
  hint,
  rightBorder = false,
  bottomBorder = false,
  last = false,
}: {
  icon: typeof ClipboardList;
  value: string;
  label: string;
  hint?: string;
  rightBorder?: boolean;
  bottomBorder?: boolean;
  last?: boolean;
}) {
  return (
    <div
      className={cn(
        "min-h-[100px] border-line p-4 xl:min-h-0 xl:border-b-0 xl:border-r xl:p-5",
        rightBorder && "border-r",
        bottomBorder && "border-b",
        last && "xl:border-r-0",
      )}
    >
      <Icon className="h-5 w-5 text-ink-2" aria-hidden />
      <p className="mt-3 text-lg font-bold text-ink">{value}</p>
      <p className="mt-1 text-[11px] leading-4 text-ink-3">
        {label}
        {hint && <span className="ml-1 text-accent">· {hint}</span>}
      </p>
    </div>
  );
}

function PreviewCard({
  id,
  icon: Icon,
  title,
  count,
  href,
  children,
}: {
  id?: string;
  icon: typeof Heart;
  title: string;
  count: number;
  href: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 rounded-lg border border-line bg-surface p-4">
      <div className="mb-4 flex items-center gap-2">
        <Icon className="h-5 w-5 text-ink" aria-hidden />
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        <span className="ml-auto rounded-full bg-raised px-2 py-0.5 text-[11px] font-semibold text-ink-2">
          {count}
        </span>
        <Link
          href={href}
          aria-label={`Открыть раздел «${title}»`}
          className="grid h-8 w-8 place-items-center rounded-md border border-line text-ink-2 transition hover:bg-raised"
        >
          <ChevronRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
      {children}
    </section>
  );
}

function EmptyPreview({ text }: { text: string }) {
  return (
    <div className="flex min-h-16 items-center rounded-md bg-raised px-3">
      <p className="text-xs leading-5 text-ink-3">{text}</p>
    </div>
  );
}

function ProfileField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-1 break-words text-sm font-medium text-ink">{value}</dd>
    </div>
  );
}
