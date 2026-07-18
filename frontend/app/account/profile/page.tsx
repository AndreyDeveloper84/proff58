"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, logout } from "@/lib/auth";
import { MaxLinkCard } from "@/components/account/MaxLinkCard";
import { NotificationPreferencesCard } from "@/components/account/NotificationPreferencesCard";

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMe().then((data) => {
      if (!data) { router.push("/account/login"); return; }
      setUser(data);
      setLoading(false);
    });
  }, [router]);

  if (loading) return <div className="p-6">Загрузка...</div>;
  if (!user) return null;

  return (
    <div className="max-w-2xl mx-auto mt-8 p-6">
      <h1 className="text-2xl font-bold mb-6">Профиль</h1>

      <dl className="space-y-3">
        <div><dt className="text-gray-500 text-sm">Телефон</dt><dd>{String(user.phone)}</dd></div>
        <div><dt className="text-gray-500 text-sm">Имя</dt><dd>{String(user.full_name || "—")}</dd></div>
        <div><dt className="text-gray-500 text-sm">Email</dt><dd>{String(user.email || "—")}</dd></div>
        <div><dt className="text-gray-500 text-sm">Тип</dt><dd>{user.customer_type === "b2b" ? "B2B" : "B2C"}</dd></div>
      </dl>

      {Boolean(user.profile) && (
        <div className="mt-6 border-t pt-4">
          <h2 className="font-semibold mb-2">Реквизиты B2B</h2>
          <dl className="space-y-2 text-sm">
            <div><dt className="text-gray-500">Организация</dt><dd>{String((user.profile as Record<string, unknown>).company_name || "—")}</dd></div>
            <div><dt className="text-gray-500">ИНН</dt><dd>{String((user.profile as Record<string, unknown>).inn || "—")}</dd></div>
          </dl>
        </div>
      )}

      <MaxLinkCard />
      <NotificationPreferencesCard />

      <div className="mt-8 space-x-4">
        <a href="/account/orders" className="text-green-600 underline">Мои заказы</a>
        <a href="/account/wishlist" className="text-green-600 underline">Избранное</a>
        <button onClick={async () => { try { await logout(); } finally { router.push("/"); } }} className="text-red-600 underline">Выйти</button>
      </div>
    </div>
  );
}
