import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/notifications", () => ({
  getNotificationPreferences: vi.fn(),
  updateNotificationPreferences: vi.fn(),
}));

import { getNotificationPreferences, updateNotificationPreferences } from "@/lib/notifications";
import type { NotificationPreferences } from "@/lib/types";
import { NotificationPreferencesCard } from "./NotificationPreferencesCard";

const mockedGet = getNotificationPreferences as unknown as ReturnType<typeof vi.fn>;
const mockedUpdate = updateNotificationPreferences as unknown as ReturnType<typeof vi.fn>;

function prefs(overrides: Partial<NotificationPreferences> = {}): NotificationPreferences {
  return {
    max_enabled: true,
    order_updates_enabled: true,
    product_availability_enabled: true,
    marketing_enabled: false,
    marketing_consent_at: null,
    marketing_consent_version: "",
    ...overrides,
  };
}

describe("NotificationPreferencesCard", () => {
  beforeEach(() => {
    mockedGet.mockReset();
    mockedUpdate.mockReset();
  });

  it("показывает загрузку, затем переключатели с текущими значениями", async () => {
    mockedGet.mockResolvedValueOnce(prefs({ order_updates_enabled: false }));
    render(<NotificationPreferencesCard />);

    expect(screen.getByText("Загрузка настроек…")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Статусы заказов" })).toBeInTheDocument(),
    );
    expect(screen.getByRole("switch", { name: "Статусы заказов" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.getByRole("switch", { name: "Уведомления в MAX" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("показывает ошибку загрузки, если бэк недоступен", async () => {
    mockedGet.mockRejectedValueOnce(new Error("network"));
    render(<NotificationPreferencesCard />);

    await waitFor(() =>
      expect(screen.getByText("Не удалось загрузить настройки уведомлений.")).toBeInTheDocument(),
    );
  });

  it("переключение order_updates шлёт PATCH только с этим полем", async () => {
    mockedGet.mockResolvedValueOnce(prefs());
    mockedUpdate.mockResolvedValueOnce(prefs({ order_updates_enabled: false }));
    render(<NotificationPreferencesCard />);

    await waitFor(() => screen.getByRole("switch", { name: "Статусы заказов" }));
    fireEvent.click(screen.getByRole("switch", { name: "Статусы заказов" }));

    await waitFor(() =>
      expect(mockedUpdate).toHaveBeenCalledWith({ order_updates_enabled: false }),
    );
    await waitFor(() => expect(screen.getByText("Сохранено")).toBeInTheDocument());
  });

  it("включение marketing отправляет consent_version", async () => {
    mockedGet.mockResolvedValueOnce(prefs());
    mockedUpdate.mockResolvedValueOnce(
      prefs({ marketing_enabled: true, marketing_consent_at: "2026-01-01T00:00:00Z" }),
    );
    render(<NotificationPreferencesCard />);

    await waitFor(() => screen.getByRole("switch", { name: "Акции и скидки" }));
    fireEvent.click(screen.getByRole("switch", { name: "Акции и скидки" }));

    await waitFor(() =>
      expect(mockedUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ marketing_enabled: true, consent_version: expect.any(String) }),
      ),
    );
  });

  it("выключение marketing НЕ отправляет consent_version", async () => {
    mockedGet.mockResolvedValueOnce(prefs({ marketing_enabled: true }));
    mockedUpdate.mockResolvedValueOnce(prefs({ marketing_enabled: false }));
    render(<NotificationPreferencesCard />);

    await waitFor(() => screen.getByRole("switch", { name: "Акции и скидки" }));
    fireEvent.click(screen.getByRole("switch", { name: "Акции и скидки" }));

    await waitFor(() =>
      expect(mockedUpdate).toHaveBeenCalledWith({ marketing_enabled: false }),
    );
  });

  it("при ошибке сохранения откатывает переключатель и показывает сообщение", async () => {
    mockedGet.mockResolvedValueOnce(prefs({ order_updates_enabled: true }));
    mockedUpdate.mockRejectedValueOnce(new Error("Не удалось сохранить настройки."));
    render(<NotificationPreferencesCard />);

    const toggle = await screen.findByRole("switch", { name: "Статусы заказов" });
    fireEvent.click(toggle);

    await waitFor(() =>
      expect(screen.getByText("Не удалось сохранить настройки.")).toBeInTheDocument(),
    );
    expect(toggle).toHaveAttribute("aria-checked", "true"); // откат к исходному
  });
});
