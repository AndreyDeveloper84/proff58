"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, getOrders } from "@/lib/auth";

export default function OrdersPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMe().then((user) => {
      if (!user) { router.push("/account/login"); return; }
      getOrders().then((data) => { setOrders(data); setLoading(false); });
    });
  }, [router]);

  if (loading) return <div className="p-6">Загрузка...</div>;

  return (
    <div className="max-w-2xl mx-auto mt-8 p-6">
      <h1 className="text-2xl font-bold mb-6">Мои заказы</h1>

      {orders.length === 0 ? (
        <p className="text-gray-500">У вас пока нет заказов. <a href="/catalog" className="text-green-600 underline">Перейти в каталог</a></p>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => (
            <div key={String(order.id)} className="border rounded p-4">
              <div className="flex justify-between">
                <span className="font-semibold">Заказ {String(order.order_number)}</span>
                <span className="text-sm text-gray-500">{String(order.display_status)}</span>
              </div>
              <div className="text-sm text-gray-600 mt-1">
                Сумма: {String(order.total)} {String(order.currency)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
