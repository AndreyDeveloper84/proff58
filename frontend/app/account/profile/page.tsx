"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  Building2,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  Clock3,
  Edit3,
  Heart,
  LoaderCircle,
  LogOut,
  MapPin,
  PackageCheck,
  Save,
  ShieldAlert,
  Smartphone,
  Trash2,
  UserRound,
} from "lucide-react";
import { AccountDialog } from "@/components/account/AccountDialog";
import { AccountShell } from "@/components/account/AccountShell";
import { MaxLinkCard } from "@/components/account/MaxLinkCard";
import { NotificationPreferencesCard } from "@/components/account/NotificationPreferencesCard";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  changePhone,
  deleteAccount,
  getMe,
  getOrders,
  getWishlist,
  logout,
  updateMe,
  type AccountUser,
  type WishlistItem,
} from "@/lib/auth";
import { formatDate, formatPrice, pluralize } from "@/lib/format";
import { isInProgress, statusBadgeClass } from "@/lib/order-status";
import type { Order } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  isLegalEntityInn,
  isValidEmail,
  isValidInn,
  isValidKpp,
  isValidPhone,
  normalizePhone,
} from "@/lib/validation";


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

type ProfileForm = {
  full_name: string;
  email: string;
  company_name: string;
  inn: string;
  kpp: string;
  legal_address: string;
};

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<AccountUser | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [ordersFailed, setOrdersFailed] = useState(false);
  const [wishlist, setWishlist] = useState<WishlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const [profileForm, setProfileForm] = useState<ProfileForm>({
    full_name: "",
    email: "",
    company_name: "",
    inn: "",
    kpp: "",
    legal_address: "",
  });
  const [phoneOpen, setPhoneOpen] = useState(false);
  const [newPhone, setNewPhone] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [phoneSaving, setPhoneSaving] = useState(false);
  const [phoneError, setPhoneError] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteSaving, setDeleteSaving] = useState(false);
  const [deleteError, setDeleteError] = useState("");

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
        // #574: сбой загрузки не превращаем в «0 заказов» — счётчики врали бы.
        if (orderData === "error") setOrdersFailed(true);
        else setOrders(orderData);
        if (wishlistData !== "error") setWishlist(wishlistData);
        setLoading(false);
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [router]);

  const openProfileEditor = () => {
    if (!user) return;
    setProfileForm({
      full_name: user.full_name,
      email: user.email,
      company_name: user.profile?.company_name ?? "",
      inn: user.profile?.inn ?? "",
      kpp: user.profile?.kpp ?? "",
      legal_address: user.profile?.legal_address ?? "",
    });
    setEditError("");
    setEditOpen(true);
  };

  const saveProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!user || editSaving) return;

    const email = profileForm.email.trim();
    const inn = profileForm.inn.trim();
    const kpp = profileForm.kpp.trim();
    if (email && !isValidEmail(email)) {
      setEditError("Проверьте адрес электронной почты.");
      return;
    }
    if (user.customer_type === "b2b" && inn && !isValidInn(inn)) {
      setEditError("ИНН должен содержать 10 или 12 цифр.");
      return;
    }
    if (user.customer_type === "b2b" && kpp && !isValidKpp(kpp)) {
      setEditError("КПП должен содержать 9 цифр.");
      return;
    }
    if (user.customer_type === "b2b" && isLegalEntityInn(inn) && !kpp) {
      setEditError("Для организации с ИНН из 10 цифр укажите КПП.");
      return;
    }

    setEditSaving(true);
    setEditError("");
    try {
      const updated = await updateMe({
        full_name: profileForm.full_name.trim(),
        email,
        ...(user.customer_type === "b2b"
          ? {
              profile: {
                company_name: profileForm.company_name.trim(),
                inn,
                kpp,
                legal_address: profileForm.legal_address.trim(),
              },
            }
          : {}),
      });
      setUser(updated);
      setEditOpen(false);
      setNotice("Данные профиля сохранены.");
    } catch (caught) {
      setEditError(caught instanceof Error ? caught.message : "Не удалось сохранить профиль.");
    } finally {
      setEditSaving(false);
    }
  };

  const savePhone = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (phoneSaving) return;
    if (!isValidPhone(newPhone)) {
      setPhoneError("Укажите корректный российский номер телефона.");
      return;
    }
    if (!currentPassword) {
      setPhoneError("Введите текущий пароль.");
      return;
    }

    setPhoneSaving(true);
    setPhoneError("");
    try {
      await changePhone(normalizePhone(newPhone), currentPassword);
      const updated = await getMe();
      if (updated) setUser(updated);
      setPhoneOpen(false);
      setNewPhone("");
      setCurrentPassword("");
      setNotice("Телефон изменён. Новый номер нужно подтвердить через MAX.");
    } catch (caught) {
      setPhoneError(caught instanceof Error ? caught.message : "Не удалось изменить телефон.");
    } finally {
      setPhoneSaving(false);
    }
  };

  const removeAccount = async () => {
    if (deleteConfirmation !== "УДАЛИТЬ" || deleteSaving) return;
    setDeleteSaving(true);
    setDeleteError("");
    try {
      await deleteAccount();
      router.push("/");
    } catch (caught) {
      setDeleteError(caught instanceof Error ? caught.message : "Не удалось удалить аккаунт.");
      setDeleteSaving(false);
    }
  };

  const orderSummary = useMemo(() => {
    const inProgress = orders.filter(isInProgress).length;
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
        {notice && (
          <div
            role="status"
            className="flex items-start gap-3 rounded-lg border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-ink"
          >
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
            <span className="flex-1">{notice}</span>
            <button
              type="button"
              onClick={() => setNotice("")}
              className="text-xs font-semibold text-accent hover:underline"
            >
              Закрыть
            </button>
          </div>
        )}

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
                  <button
                    type="button"
                    onClick={openProfileEditor}
                    className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-accent hover:underline"
                  >
                    <Edit3 className="h-3.5 w-3.5" aria-hidden />
                    Редактировать профиль
                  </button>
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

            {ordersFailed ? (
              <div className="px-4 py-10 text-center">
                <p className="text-sm font-semibold text-danger">Не удалось загрузить заказы</p>
                <p className="mt-1 text-xs text-ink-3">
                  Обновите страницу — заказы никуда не пропали.
                </p>
              </div>
            ) : orders.length === 0 ? (
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
                        от {formatDate(order.created_at)}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "w-fit rounded-md px-2 py-1 text-[11px] font-semibold",
                        statusBadgeClass(order),
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
                      href={`/account/orders/${encodeURIComponent(order.order_number)}`}
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
            id="notifications-preview"
            icon={Clock3}
            title="Уведомления"
            count={orderSummary.inProgress}
            href="/account/notifications"
          >
            <EmptyPreview
              text={
                orderSummary.inProgress > 0
                  ? "Новые статусы заказов доступны в центре уведомлений"
                  : "Здесь появятся изменения статусов заказов"
              }
            />
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
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={openProfileEditor}
                className="inline-flex min-h-10 items-center gap-2 rounded-md border border-line px-3 text-sm font-semibold text-ink transition hover:bg-raised"
              >
                <Edit3 className="h-4 w-4" aria-hidden />
                Редактировать
              </button>
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

          <button
            type="button"
            onClick={() => {
              setNewPhone(user.phone);
              setCurrentPassword("");
              setPhoneError("");
              setPhoneOpen(true);
            }}
            className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-md border border-line px-3 text-sm font-semibold text-ink transition hover:bg-raised"
          >
            <Smartphone className="h-4 w-4 text-accent" aria-hidden />
            Сменить телефон
          </button>

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

          <MaxLinkCard />
          <NotificationPreferencesCard />
        </section>

        <section className="rounded-lg border border-danger/30 bg-surface p-5 lg:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-danger/10 text-danger">
                <ShieldAlert className="h-5 w-5" aria-hidden />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-ink">Удаление аккаунта</h2>
                <p className="mt-1 max-w-2xl text-xs leading-5 text-ink-3">
                  Профиль будет отключён, персональные данные обезличены, а товары из
                  избранного удалены. Бухгалтерские записи о заказах сохранятся без ваших
                  персональных данных.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                setDeleteConfirmation("");
                setDeleteError("");
                setDeleteOpen(true);
              }}
              className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-danger/40 px-4 text-sm font-semibold text-danger transition hover:bg-red-50"
            >
              <Trash2 className="h-4 w-4" aria-hidden />
              Удалить аккаунт
            </button>
          </div>
        </section>
      </div>

      <AccountDialog
        open={editOpen}
        onClose={() => {
          if (!editSaving) setEditOpen(false);
        }}
        title="Редактирование профиля"
        description="Обновите контактные данные, которые используются в личном кабинете и новых заказах."
      >
        <form onSubmit={saveProfile} className="space-y-5 p-5 sm:p-6" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Имя">
              {(control) => (
                <Input
                  {...control}
                  value={profileForm.full_name}
                  onChange={(event) =>
                    setProfileForm((current) => ({
                      ...current,
                      full_name: event.target.value,
                    }))
                  }
                  autoComplete="name"
                />
              )}
            </Field>
            <Field label="Email">
              {(control) => (
                <Input
                  {...control}
                  type="email"
                  value={profileForm.email}
                  onChange={(event) =>
                    setProfileForm((current) => ({
                      ...current,
                      email: event.target.value,
                    }))
                  }
                  autoComplete="email"
                />
              )}
            </Field>
          </div>

          {user.customer_type === "b2b" && (
            <div className="border-t border-line pt-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Building2 className="h-4 w-4 text-accent" aria-hidden />
                Реквизиты компании
              </h3>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <Field label="Организация">
                  {(control) => (
                    <Input
                      {...control}
                      value={profileForm.company_name}
                      onChange={(event) =>
                        setProfileForm((current) => ({
                          ...current,
                          company_name: event.target.value,
                        }))
                      }
                      autoComplete="organization"
                    />
                  )}
                </Field>
                <Field label="ИНН" hint="10 цифр для организации или 12 для ИП">
                  {(control) => (
                    <Input
                      {...control}
                      inputMode="numeric"
                      value={profileForm.inn}
                      onChange={(event) =>
                        setProfileForm((current) => ({
                          ...current,
                          inn: event.target.value.replace(/\D/g, "").slice(0, 12),
                        }))
                      }
                    />
                  )}
                </Field>
                <Field label="КПП" hint="9 цифр; для ИП можно оставить пустым">
                  {(control) => (
                    <Input
                      {...control}
                      inputMode="numeric"
                      value={profileForm.kpp}
                      onChange={(event) =>
                        setProfileForm((current) => ({
                          ...current,
                          kpp: event.target.value.replace(/\D/g, "").slice(0, 9),
                        }))
                      }
                    />
                  )}
                </Field>
                <Field label="Юридический адрес" className="sm:col-span-2">
                  {(control) => (
                    <Textarea
                      {...control}
                      rows={3}
                      value={profileForm.legal_address}
                      onChange={(event) =>
                        setProfileForm((current) => ({
                          ...current,
                          legal_address: event.target.value,
                        }))
                      }
                      autoComplete="street-address"
                    />
                  )}
                </Field>
              </div>
            </div>
          )}

          {editError && (
            <p
              role="alert"
              className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {editError}
            </p>
          )}
          <div className="flex flex-col-reverse gap-2 border-t border-line pt-5 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => setEditOpen(false)}
              disabled={editSaving}
              className="h-11 rounded-md border border-line px-5 text-sm font-semibold text-ink transition hover:bg-raised disabled:opacity-50"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={editSaving}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
            >
              {editSaving ? (
                <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Save className="h-4 w-4" aria-hidden />
              )}
              {editSaving ? "Сохраняем…" : "Сохранить"}
            </button>
          </div>
        </form>
      </AccountDialog>

      <AccountDialog
        open={phoneOpen}
        onClose={() => {
          if (!phoneSaving) setPhoneOpen(false);
        }}
        title="Смена телефона"
        description="Для безопасности подтвердите действие текущим паролем. Новый номер потребуется заново подтвердить через MAX."
      >
        <form onSubmit={savePhone} className="space-y-4 p-5 sm:p-6" noValidate>
          <Field label="Новый телефон" required>
            {(control) => (
              <Input
                {...control}
                type="tel"
                value={newPhone}
                onChange={(event) => setNewPhone(event.target.value)}
                placeholder="+7 999 123-45-67"
                autoComplete="tel"
              />
            )}
          </Field>
          <Field label="Текущий пароль" required>
            {(control) => (
              <Input
                {...control}
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                autoComplete="current-password"
              />
            )}
          </Field>
          {phoneError && (
            <p
              role="alert"
              className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {phoneError}
            </p>
          )}
          <div className="flex flex-col-reverse gap-2 border-t border-line pt-5 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => setPhoneOpen(false)}
              disabled={phoneSaving}
              className="h-11 rounded-md border border-line px-5 text-sm font-semibold text-ink transition hover:bg-raised disabled:opacity-50"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={phoneSaving}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
            >
              {phoneSaving && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />}
              {phoneSaving ? "Меняем…" : "Сменить телефон"}
            </button>
          </div>
        </form>
      </AccountDialog>

      <AccountDialog
        open={deleteOpen}
        onClose={() => {
          if (!deleteSaving) setDeleteOpen(false);
        }}
        title="Удалить аккаунт?"
        description="Это действие нельзя отменить. Профиль станет недоступен сразу после удаления."
        danger
      >
        <div className="space-y-4 p-5 sm:p-6">
          <div className="rounded-md bg-raised p-4 text-sm leading-6 text-ink-2">
            Заказы сохранятся только как обезличенные бухгалтерские документы. Персональные
            данные, профиль компании и избранное будут удалены.
          </div>
          <Field label="Для подтверждения введите УДАЛИТЬ" required>
            {(control) => (
              <Input
                {...control}
                value={deleteConfirmation}
                onChange={(event) => setDeleteConfirmation(event.target.value)}
                autoComplete="off"
              />
            )}
          </Field>
          {deleteError && (
            <p
              role="alert"
              className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
            >
              {deleteError}
            </p>
          )}
          <div className="flex flex-col-reverse gap-2 border-t border-line pt-5 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => setDeleteOpen(false)}
              disabled={deleteSaving}
              className="h-11 rounded-md border border-line px-5 text-sm font-semibold text-ink transition hover:bg-raised disabled:opacity-50"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={() => void removeAccount()}
              disabled={deleteConfirmation !== "УДАЛИТЬ" || deleteSaving}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-danger px-5 text-sm font-semibold text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {deleteSaving ? (
                <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <Trash2 className="h-4 w-4" aria-hidden />
              )}
              {deleteSaving ? "Удаляем…" : "Удалить навсегда"}
            </button>
          </div>
        </div>
      </AccountDialog>
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
