"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { getMe } from "@/lib/auth";
import {
  getNotificationHistory,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/notifications";
import type { NotificationItem } from "@/lib/types";

const PAGE_SIZE = 20;

// Центр уведомлений (#513 epic, Phase 2 отложенная часть #519): история +
// прочитано/непрочитано поверх готового backend API (#515). Сервер — источник
// истины по факту прочтения; клик по непрочитанному — оптимистичный апдейт с
// откатом при ошибке (тот же паттерн, что NotificationPreferencesCard).
export default function NotificationsPage() {
  const router = useRouter();
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  // Явный счётчик "сколько уже запрошено", а не items.length: под конкурентную
  // вставку нового уведомления между подгрузками страниц (обычное дело для
  // живой ленты) длина уже отрендеренного не обязана совпадать с реальным
  // server-side offset, использованным для последнего запроса.
  const [nextOffset, setNextOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [markingAll, setMarkingAll] = useState(false);

  const loadPage = useCallback(async (offset: number) => {
    const page = await getNotificationHistory(offset, PAGE_SIZE);
    setItems((prev) => (offset === 0 ? page.results : [...(prev ?? []), ...page.results]));
    setHasMore(page.next !== null);
    setNextOffset(offset + page.results.length);
  }, []);

  useEffect(() => {
    let active = true;
    getMe().then((user) => {
      if (!active) return;
      if (!user) {
        router.push("/account/login");
        return;
      }
      loadPage(0).catch(() => {
        if (active) setError("Не удалось загрузить уведомления.");
      });
    });
    return () => {
      active = false;
    };
  }, [router, loadPage]);

  async function handleLoadMore() {
    setLoadingMore(true);
    try {
      await loadPage(nextOffset);
    } catch {
      setError("Не удалось загрузить уведомления.");
    } finally {
      setLoadingMore(false);
    }
  }

  // Откат по failure — точечный, через функциональный setState (id/список id, а
  // не снимок ВСЕГО items "до"): при двух параллельных операциях (напр. клик по
  // двум разным уведомлениям подряд, одна из них падает) откат к целому снимку
  // стёр бы уже успешно применённое обновление другой — здесь так не бывает.
  async function handleMarkRead(id: number) {
    setItems((prev) =>
      (prev ?? []).map((n) => (n.id === id && !n.read_at ? { ...n, read_at: new Date().toISOString() } : n)),
    );
    try {
      await markNotificationRead(id);
    } catch {
      setItems((prev) => (prev ?? []).map((n) => (n.id === id ? { ...n, read_at: null } : n)));
    }
  }

  async function handleMarkAllRead() {
    setMarkingAll(true);
    const now = new Date().toISOString();
    const flippedIds = (items ?? []).filter((n) => !n.read_at).map((n) => n.id);
    setItems((prev) => (prev ?? []).map((n) => (n.read_at ? n : { ...n, read_at: now })));
    try {
      await markAllNotificationsRead();
    } catch {
      const flipped = new Set(flippedIds);
      setItems((prev) => (prev ?? []).map((n) => (flipped.has(n.id) ? { ...n, read_at: null } : n)));
    } finally {
      setMarkingAll(false);
    }
  }

  const unreadCount = items?.filter((n) => !n.read_at).length ?? 0;

  return (
    <div className="mx-auto mt-8 max-w-2xl p-6">
      <div className="mb-6 flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-ink">Уведомления</h1>
        {unreadCount > 0 && (
          <Button variant="outline" size="sm" onClick={handleMarkAllRead} disabled={markingAll}>
            <Check className="h-4 w-4" aria-hidden />
            Прочитать всё
          </Button>
        )}
      </div>

      {error && !items && (
        <ErrorState description={error} action={<Button onClick={() => location.reload()}>Обновить</Button>} />
      )}

      {!error && items === null && <LoadingState label="Загрузка уведомлений…" />}

      {items !== null && items.length === 0 && (
        <EmptyState
          icon={<Bell className="h-10 w-10" aria-hidden />}
          title="Пока нет уведомлений"
          description="Здесь появятся статусы заказов, поступление товаров и другие MAX-уведомления."
        />
      )}

      {items !== null && items.length > 0 && (
        <div className="space-y-2">
          {items.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => handleMarkRead(n.id)}
              disabled={!!n.read_at}
              className="flex w-full flex-col gap-1 rounded-md border border-line bg-surface p-3 text-left transition disabled:cursor-default enabled:hover:bg-raised"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 font-medium text-ink">
                  {!n.read_at && <span className="h-2 w-2 shrink-0 rounded-full bg-accent" aria-hidden />}
                  {n.title}
                </span>
                <span className="shrink-0 text-xs text-ink-3">
                  {new Date(n.created_at).toLocaleString("ru-RU", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <p className="text-sm text-ink-2">{n.body}</p>
            </button>
          ))}

          {hasMore && (
            <div className="pt-2 text-center">
              <Button variant="outline" onClick={handleLoadMore} disabled={loadingMore}>
                {loadingMore ? "Загрузка…" : "Показать ещё"}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
