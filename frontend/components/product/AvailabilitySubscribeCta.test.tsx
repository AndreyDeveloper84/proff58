import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return { ...actual, getMe: vi.fn(), maxAccountStatus: vi.fn() };
});
vi.mock("@/lib/notifications", () => ({
  getAvailabilitySubscriptionStatus: vi.fn(),
  subscribeAvailability: vi.fn(),
  unsubscribeAvailability: vi.fn(),
}));

import { ApiError } from "@/lib/api";
import { getMe, maxAccountStatus } from "@/lib/auth";
import {
  getAvailabilitySubscriptionStatus,
  subscribeAvailability,
  unsubscribeAvailability,
} from "@/lib/notifications";
import { AvailabilitySubscribeCta } from "./AvailabilitySubscribeCta";

const mockedGetMe = getMe as unknown as ReturnType<typeof vi.fn>;
const mockedMaxStatus = maxAccountStatus as unknown as ReturnType<typeof vi.fn>;
const mockedGetSub = getAvailabilitySubscriptionStatus as unknown as ReturnType<typeof vi.fn>;
const mockedSubscribe = subscribeAvailability as unknown as ReturnType<typeof vi.fn>;
const mockedUnsubscribe = unsubscribeAvailability as unknown as ReturnType<typeof vi.fn>;

describe("AvailabilitySubscribeCta", () => {
  beforeEach(() => {
    mockedGetMe.mockReset();
    mockedMaxStatus.mockReset();
    mockedGetSub.mockReset();
    mockedSubscribe.mockReset();
    mockedUnsubscribe.mockReset();
    // Дефолт для тестов, которым статус подписки не важен — «нет подписки».
    // Тесты, которым важен другой статус, переопределяют через mockResolvedValueOnce.
    mockedGetSub.mockResolvedValue({ status: null });
  });

  it("гость: клик по CTA ведёт на логин с ?next= на PDP (AC: auth expiry/не авторизован)", async () => {
    mockedGetMe.mockResolvedValue(null);
    const original = window.location;
    // jsdom не даёт реально перейти по ссылке — подменяем location на объект,
    // где можно проверить присвоенный href.
    Object.defineProperty(window, "location", {
      value: { ...original, href: "" },
      writable: true,
    });

    render(<AvailabilitySubscribeCta productSlug="drel-1" />);
    const button = await screen.findByRole("button", { name: "Сообщить о поступлении" });
    fireEvent.click(button);

    await waitFor(() =>
      expect(window.location.href).toBe(
        `/account/login?next=${encodeURIComponent("/product/drel-1")}`,
      ),
    );
    Object.defineProperty(window, "location", { value: original, writable: true });
  });

  it("авторизован, MAX не подключён: клик показывает inline-приглашение подключить MAX", async () => {
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedMaxStatus.mockResolvedValue({ linked: false });
    render(<AvailabilitySubscribeCta productSlug="drel-1" />);

    const button = await screen.findByRole("button", { name: "Сообщить о поступлении" });
    fireEvent.click(button);

    await waitFor(() =>
      expect(screen.getByText("Чтобы получить уведомление, подключите MAX:")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Подключить MAX" })).toBeInTheDocument();
  });

  it("авторизован + MAX подключён: подписка показывает success-состояние с отменой", async () => {
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedMaxStatus.mockResolvedValue({ linked: true });
    mockedSubscribe.mockResolvedValueOnce({ status: "active" });
    render(<AvailabilitySubscribeCta productSlug="drel-1" />);

    const button = await screen.findByRole("button", { name: "Сообщить о поступлении" });
    fireEvent.click(button);

    await waitFor(() => expect(screen.getByText("Мы сообщим вам в MAX")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Отменить" })).toBeInTheDocument();
  });

  it("уже подписан при загрузке карточки — сразу показывает success-состояние", async () => {
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedGetSub.mockResolvedValueOnce({ status: "active" });
    render(<AvailabilitySubscribeCta productSlug="drel-1" />);

    await waitFor(() => expect(screen.getByText("Мы сообщим вам в MAX")).toBeInTheDocument());
  });

  it("отмена подписки возвращает кнопку в исходное состояние", async () => {
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedGetSub.mockResolvedValueOnce({ status: "active" });
    mockedUnsubscribe.mockResolvedValueOnce(undefined);
    render(<AvailabilitySubscribeCta productSlug="drel-1" />);

    const cancelButton = await screen.findByRole("button", { name: "Отменить" });
    fireEvent.click(cancelButton);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Сообщить о поступлении" })).toBeInTheDocument(),
    );
  });

  it("actionable-текст для already_in_stock", async () => {
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedMaxStatus.mockResolvedValue({ linked: true });
    mockedSubscribe.mockRejectedValueOnce(new ApiError("Товар сейчас в наличии.", 400, "already_in_stock"));
    render(<AvailabilitySubscribeCta productSlug="drel-1" />);

    const button = await screen.findByRole("button", { name: "Сообщить о поступлении" });
    fireEvent.click(button);

    await waitFor(() =>
      expect(screen.getByText("Товар уже в наличии — обновите страницу.")).toBeInTheDocument(),
    );
  });

  it("actionable-текст для max_connection_required", async () => {
    mockedGetMe.mockResolvedValue({ id: 1 });
    mockedMaxStatus.mockResolvedValue({ linked: true });
    mockedSubscribe.mockRejectedValueOnce(
      new ApiError("Нужна активная привязка MAX.", 400, "max_connection_required"),
    );
    render(<AvailabilitySubscribeCta productSlug="drel-1" />);

    const button = await screen.findByRole("button", { name: "Сообщить о поступлении" });
    fireEvent.click(button);

    await waitFor(() =>
      expect(
        screen.getByText("Нужна активная привязка MAX. Подключите её и попробуйте снова."),
      ).toBeInTheDocument(),
    );
  });
});
