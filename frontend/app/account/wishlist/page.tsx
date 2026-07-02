"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getMe, getWishlist } from "@/lib/auth";

export default function WishlistPage() {
  const router = useRouter();
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMe().then((user) => {
      if (!user) { router.push("/account/login"); return; }
      getWishlist().then((data) => { setItems(data); setLoading(false); });
    });
  }, [router]);

  if (loading) return <div className="p-6">Загрузка...</div>;

  return (
    <div className="max-w-2xl mx-auto mt-8 p-6">
      <h1 className="text-2xl font-bold mb-6">Избранное</h1>

      {items.length === 0 ? (
        <p className="text-gray-500">Список пуст. <Link href="/catalog" className="text-green-600 underline">Перейти в каталог</Link></p>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <a
              key={String(item.product_id)}
              href={`/product/${String(item.product_slug)}`}
              className="block border rounded p-3 hover:bg-gray-50"
            >
              {String(item.product_name)}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
