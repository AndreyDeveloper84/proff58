import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const replaceMock = vi.fn();
const routerMock = { push: pushMock, replace: replaceMock };

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/account/profile",
}));
vi.mock("@/lib/auth", () => ({
  changePhone: vi.fn(),
  checkAuth: vi.fn(),
  deleteAccount: vi.fn(),
  getMe: vi.fn(),
  getOrders: vi.fn(),
  getWishlist: vi.fn(),
  loginHref: (next?: string) =>
    next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login",
  logout: vi.fn(),
  updateMe: vi.fn(),
}));
vi.mock("@/components/account/MaxLinkCard", () => ({
  MaxLinkCard: () => <div>Настройки MAX</div>,
}));
vi.mock("@/components/account/NotificationPreferencesCard", () => ({
  NotificationPreferencesCard: () => <div>Настройки уведомлений</div>,
}));

import { deleteAccount, checkAuth, getOrders, getWishlist, updateMe } from "@/lib/auth";
import ProfilePage from "./page";

const mockedGetMe = checkAuth as unknown as ReturnType<typeof vi.fn>;
const mockedGetOrders = getOrders as unknown as ReturnType<typeof vi.fn>;
const mockedGetWishlist = getWishlist as unknown as ReturnType<typeof vi.fn>;
const mockedUpdateMe = updateMe as unknown as ReturnType<typeof vi.fn>;
const mockedDeleteAccount = deleteAccount as unknown as ReturnType<typeof vi.fn>;

describe("ProfilePage dashboard", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetOrders.mockReset();
    mockedGetWishlist.mockReset();
    mockedUpdateMe.mockReset();
    mockedDeleteAccount.mockReset();
    mockedGetMe.mockResolvedValue({
      id: 1,
      phone: "+79001112233",
      email: "ivan@example.com",
      full_name: "Иван Иванов",
      customer_type: "b2b",
      profile: {
        company_name: "ООО Инструмент",
        inn: "5800000000",
        kpp: "580001001",
        legal_address: "г. Пенза, ул. Ленина, 1",
      },
    });
    mockedGetOrders.mockResolvedValue([
      {
        id: 10,
        order_number: "П-2026-0010",
        // Реальные значения бэка: display_status — только текст, логика по осям.
        fulfillment_status: "confirmed",
        payment_status: "paid",
        display_status: "Подтверждён",
        total: "18990.00",
        currency: "RUB",
        created_at: "2026-07-19T10:00:00Z",
        delivery_address: "г. Пенза, ул. Ленина, 1",
        items: [],
      },
    ]);
    mockedGetWishlist.mockResolvedValue([
      {
        product_id: 7,
        product_name: "Дрель аккумуляторная",
        product_slug: "drel-akkumulyatornaya",
      },
    ]);
  });

  it("показывает сводку по реальному пользователю, заказам и избранному", async () => {
    render(<ProfilePage />);

    expect(await screen.findByText("Добро пожаловать!")).toBeInTheDocument();
    expect(screen.getAllByText("Иван Иванов").length).toBeGreaterThan(0);
    expect(screen.getByText("№ П-2026-0010")).toBeInTheDocument();
    expect(screen.getAllByText("18 990 ₽").length).toBeGreaterThan(0);
    expect(screen.getByText("Дрель аккумуляторная")).toBeInTheDocument();
    expect(screen.getAllByText("ООО Инструмент").length).toBeGreaterThan(0);
    expect(screen.getByText("Настройки MAX")).toBeInTheDocument();
  });

  it("неавторизованного пользователя отправляет на вход", async () => {
    mockedGetMe.mockResolvedValueOnce("anonymous");
    render(<ProfilePage />);

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/account/login?next=%2Faccount%2Fprofile"));
  });

  it("редактирует профиль и сразу обновляет данные на странице", async () => {
    mockedUpdateMe.mockResolvedValueOnce({
      id: 1,
      phone: "+79001112233",
      email: "new@example.com",
      full_name: "Иван Петров",
      customer_type: "b2b",
      profile: {
        company_name: "ООО Инструмент",
        inn: "5800000000",
        kpp: "580001001",
        legal_address: "г. Пенза, ул. Ленина, 1",
      },
    });
    render(<ProfilePage />);

    await screen.findByText("Добро пожаловать!");
    fireEvent.click(screen.getByRole("button", { name: "Редактировать профиль" }));
    fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "Иван Петров" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(mockedUpdateMe).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name: "Иван Петров",
          email: "new@example.com",
        }),
      ),
    );
    expect(await screen.findByText("Данные профиля сохранены.")).toBeInTheDocument();
    expect(screen.getAllByText("Иван Петров").length).toBeGreaterThan(0);
  });

  it("удаляет аккаунт только после текстового подтверждения", async () => {
    mockedDeleteAccount.mockResolvedValueOnce(undefined);
    render(<ProfilePage />);

    await screen.findByText("Добро пожаловать!");
    fireEvent.click(screen.getByRole("button", { name: "Удалить аккаунт" }));
    const deleteButton = screen.getByRole("button", { name: "Удалить навсегда" });
    expect(deleteButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Для подтверждения введите УДАЛИТЬ/), {
      target: { value: "УДАЛИТЬ" },
    });
    fireEvent.click(deleteButton);

    await waitFor(() => expect(mockedDeleteAccount).toHaveBeenCalledTimes(1));
    expect(pushMock).toHaveBeenCalledWith("/");
  });
});
