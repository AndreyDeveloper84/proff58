import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
// Стабильная ссылка (как настоящий useRouter()) — иначе [router, loadPage] в
// useEffect видел бы новый router каждый рендер и гонял эффект по кругу.
const routerMock = { push: pushMock };
vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/account/notifications",
}));
vi.mock("@/lib/auth", () => ({ getMe: vi.fn() }));
vi.mock("@/lib/notifications", () => ({
  getNotificationHistory: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}));

import { getMe } from "@/lib/auth";
import {
  getNotificationHistory,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/notifications";
import type { NotificationItem } from "@/lib/types";
import NotificationsPage from "./page";

const mockedGetMe = getMe as unknown as ReturnType<typeof vi.fn>;
const mockedHistory = getNotificationHistory as unknown as ReturnType<typeof vi.fn>;
const mockedMarkAll = markAllNotificationsRead as unknown as ReturnType<typeof vi.fn>;
const mockedMarkOne = markNotificationRead as unknown as ReturnType<typeof vi.fn>;

function item(overrides: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: 1,
    event: "order_confirmed",
    category: "order_updates",
    title: "Заказ подтверждён",
    body: "Заказ №1 подтверждён.",
    data: {},
    policy_skip_reason: "",
    created_at: "2026-07-18T10:00:00Z",
    read_at: null,
    ...overrides,
  };
}

describe("NotificationsPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
    mockedGetMe.mockReset();
    mockedHistory.mockReset();
    mockedMarkAll.mockReset();
    mockedMarkOne.mockReset();
    mockedGetMe.mockResolvedValue({ id: 1 });
  });

  it("неавторизованного гостя редиректит на логин", async () => {
    mockedGetMe.mockResolvedValueOnce(null);
    render(<NotificationsPage />);
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/account/login"));
  });

  it("показывает пустое состояние, если уведомлений нет", async () => {
    mockedHistory.mockResolvedValueOnce({ count: 0, next: null, previous: null, results: [] });
    render(<NotificationsPage />);
    await waitFor(() => expect(screen.getByText("Пока нет уведомлений")).toBeInTheDocument());
  });

  it("показывает список и бейдж непрочитанного у новых уведомлений", async () => {
    mockedHistory.mockResolvedValueOnce({
      count: 2,
      next: null,
      previous: null,
      results: [item({ id: 1, read_at: null }), item({ id: 2, title: "Заказ доставлен", read_at: "2026-07-18T09:00:00Z" })],
    });
    render(<NotificationsPage />);
    await waitFor(() => expect(screen.getByText("Заказ подтверждён")).toBeInTheDocument());
    expect(screen.getByText("Заказ доставлен")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Прочитать всё" })).toBeInTheDocument();
  });

  it("не показывает «Прочитать всё», если всё уже прочитано", async () => {
    mockedHistory.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [item({ read_at: "2026-07-18T09:00:00Z" })],
    });
    render(<NotificationsPage />);
    await waitFor(() => expect(screen.getByText("Заказ подтверждён")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Прочитать всё" })).not.toBeInTheDocument();
  });

  it("клик по непрочитанному уведомлению отмечает его прочитанным", async () => {
    mockedHistory.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [item({ read_at: null })],
    });
    mockedMarkOne.mockResolvedValueOnce(item({ read_at: "2026-07-18T10:05:00Z" }));
    render(<NotificationsPage />);

    const row = await screen.findByRole("button", { name: /Заказ подтверждён/ });
    fireEvent.click(row);

    await waitFor(() => expect(mockedMarkOne).toHaveBeenCalledWith(1));
    await waitFor(() => expect(row).toBeDisabled());
  });

  it("при ошибке отмены прочитанным откатывает именно эту строку", async () => {
    mockedHistory.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [item({ read_at: null })],
    });
    mockedMarkOne.mockRejectedValueOnce(new Error("network"));
    render(<NotificationsPage />);

    const row = await screen.findByRole("button", { name: /Заказ подтверждён/ });
    fireEvent.click(row);

    await waitFor(() => expect(mockedMarkOne).toHaveBeenCalledWith(1));
    await waitFor(() => expect(row).not.toBeDisabled());
  });

  it("регресс: провал отметки одного уведомления не откатывает уже применённое обновление другого", async () => {
    // Раньше откат делался через снимок ВСЕГО items "до" — здесь он стёр бы
    // успешно применённое обновление второй строки. Теперь откат точечный.
    mockedHistory.mockResolvedValueOnce({
      count: 2,
      next: null,
      previous: null,
      results: [item({ id: 1, title: "Первое" }), item({ id: 2, title: "Второе" })],
    });
    let rejectFirst!: (e: Error) => void;
    const firstCall = new Promise<NotificationItem>((_resolve, reject) => {
      rejectFirst = reject;
    });
    mockedMarkOne.mockReturnValueOnce(firstCall);
    mockedMarkOne.mockResolvedValueOnce(item({ id: 2, title: "Второе", read_at: "2026-07-18T10:05:00Z" }));

    render(<NotificationsPage />);
    const first = await screen.findByRole("button", { name: /Первое/ });
    const second = await screen.findByRole("button", { name: /Второе/ });

    fireEvent.click(first); // запрос №1 в полёте (ещё не разрешён)
    fireEvent.click(second); // запрос №2 — успеет отработать первым

    await waitFor(() => expect(second).toBeDisabled()); // второе уже прочитано
    rejectFirst(new Error("network")); // теперь первое падает

    await waitFor(() => expect(first).not.toBeDisabled()); // первое откатилось
    expect(second).toBeDisabled(); // а второе осталось прочитанным, не откатилось
  });

  it("«Прочитать всё» помечает все непрочитанные и скрывает кнопку", async () => {
    mockedHistory.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [item({ read_at: null })],
    });
    mockedMarkAll.mockResolvedValueOnce({ marked: 1 });
    render(<NotificationsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Прочитать всё" }));

    await waitFor(() => expect(mockedMarkAll).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Прочитать всё" })).not.toBeInTheDocument(),
    );
  });

  it("при ошибке «Прочитать всё» откатывает и снова показывает кнопку", async () => {
    mockedHistory.mockResolvedValueOnce({
      count: 1,
      next: null,
      previous: null,
      results: [item({ read_at: null })],
    });
    mockedMarkAll.mockRejectedValueOnce(new Error("network"));
    render(<NotificationsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Прочитать всё" }));

    await waitFor(() => expect(mockedMarkAll).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Прочитать всё" })).toBeInTheDocument(),
    );
  });

  it("«Показать ещё» подгружает следующую страницу", async () => {
    mockedHistory
      .mockResolvedValueOnce({
        count: 2,
        next: "http://x/?limit=20&offset=20",
        previous: null,
        results: [item({ id: 1 })],
      })
      .mockResolvedValueOnce({
        count: 2,
        next: null,
        previous: null,
        results: [item({ id: 2, title: "Вторая страница" })],
      });
    render(<NotificationsPage />);

    const more = await screen.findByRole("button", { name: "Показать ещё" });
    fireEvent.click(more);

    await waitFor(() => expect(screen.getByText("Вторая страница")).toBeInTheDocument());
    expect(mockedHistory).toHaveBeenLastCalledWith(1, 20);
    expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();
  });

  it("показывает ошибку загрузки, если история недоступна", async () => {
    mockedHistory.mockRejectedValueOnce(new Error("network"));
    render(<NotificationsPage />);
    await waitFor(() =>
      expect(screen.getByText("Не удалось загрузить уведомления.")).toBeInTheDocument(),
    );
  });
});
