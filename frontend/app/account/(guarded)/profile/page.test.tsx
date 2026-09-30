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
  isReauthRequired: (e: unknown) =>
    Boolean(e && typeof e === "object" && (e as { code?: string }).code === "reauth_required"),
  isReauthValid: (u: { reauth_valid_until?: string | null } | null) =>
    Boolean(u?.reauth_valid_until) && new Date(u!.reauth_valid_until!).getTime() > Date.now(),
  loginHref: (next?: string) =>
    next ? `/account/login?next=${encodeURIComponent(next)}` : "/account/login",
  logout: vi.fn(),
  updateMe: vi.fn(),
}));
vi.mock("@/components/account/MaxLinkCard", () => ({
  MaxLinkCard: () => <div>Настройки MAX</div>,
}));
vi.mock("@/components/account/OAuthLinksCard", () => ({
  OAuthLinksCard: () => <div>Вход через VK ID и Яндекс ID</div>,
}));
vi.mock("@/components/account/ReauthPanel", () => ({
  ReauthPanel: ({ next, onVerified }: { next: string; onVerified: () => void }) => (
    <div>
      Подтвердите, что это вы · {next}
      <button type="button" onClick={onVerified}>
        Подтвердить (заглушка)
      </button>
    </div>
  ),
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

const baseUser = {
  id: 1,
  phone: "+79001112233",
  email: "ivan@example.com",
  full_name: "Иван Иванов",
  customer_type: "b2b" as const,
  profile: {
    company_name: "ООО Инструмент",
    inn: "5800000000",
    kpp: "580001001",
    legal_address: "г. Пенза, ул. Ленина, 1",
  },
};

describe("ProfilePage dashboard", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetOrders.mockReset();
    mockedGetWishlist.mockReset();
    mockedUpdateMe.mockReset();
    mockedDeleteAccount.mockReset();
    mockedGetMe.mockResolvedValue(baseUser);
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
    expect(mockedDeleteAccount).toHaveBeenCalledWith(undefined);
    expect(pushMock).toHaveBeenCalledWith("/");
  });

  it("у аккаунта с паролем удаление требует пароль", async () => {
    mockedGetMe.mockResolvedValueOnce({ ...baseUser, has_password: true });
    mockedDeleteAccount.mockResolvedValueOnce(undefined);
    render(<ProfilePage />);

    await screen.findByText("Добро пожаловать!");
    fireEvent.click(screen.getByRole("button", { name: "Удалить аккаунт" }));
    fireEvent.change(screen.getByLabelText(/Для подтверждения введите УДАЛИТЬ/), {
      target: { value: "УДАЛИТЬ" },
    });
    const deleteButton = screen.getByRole("button", { name: "Удалить навсегда" });
    expect(deleteButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^Пароль/), { target: { value: "secret" } });
    fireEvent.click(deleteButton);

    await waitFor(() => expect(mockedDeleteAccount).toHaveBeenCalledWith("secret"));
  });

  // ═══════════ DRF-2497: подтверждение личности ═══════════

  it("без пароля: сервер просит подтвердить — в диалоге удаления появляется панель", async () => {
    mockedDeleteAccount.mockRejectedValueOnce(
      Object.assign(new Error("Подтвердите, что это вы: войдите ещё раз."), {
        code: "reauth_required",
      }),
    );
    render(<ProfilePage />);

    await screen.findByText("Добро пожаловать!");
    fireEvent.click(screen.getByRole("button", { name: "Удалить аккаунт" }));
    fireEvent.change(screen.getByLabelText(/Для подтверждения введите УДАЛИТЬ/), {
      target: { value: "УДАЛИТЬ" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Удалить навсегда" }));

    expect(
      await screen.findByText(/Подтвердите, что это вы · \/account\/profile\?resume=delete/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(pushMock).not.toHaveBeenCalled();

    // Подтвердили — действие само не повторяется, человек жмёт кнопку ещё раз.
    mockedDeleteAccount.mockResolvedValueOnce(undefined);
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить (заглушка)" }));
    expect(
      await screen.findByText("Подтверждено. Нажмите «Удалить навсегда» ещё раз."),
    ).toBeInTheDocument();
    expect(mockedDeleteAccount).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Удалить навсегда" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
  });

  it("возврат с resume=delete без подтверждения на сервере ничего не обещает", async () => {
    window.history.replaceState(null, "", "/account/profile?resume=delete&reauth=ok");
    mockedGetMe.mockResolvedValueOnce({ ...baseUser, reauth_valid_until: null });
    render(<ProfilePage />);

    await screen.findByText("Добро пожаловать!");
    expect(screen.queryByText(/Вход подтверждён/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Удалить навсегда" })).toBeNull();
    expect(window.location.search).toBe("");
  });

  it("возврат с resume=delete при подтверждении открывает диалог удаления", async () => {
    window.history.replaceState(null, "", "/account/profile?resume=delete&reauth=ok");
    mockedGetMe.mockResolvedValueOnce({
      ...baseUser,
      reauth_valid_until: new Date(Date.now() + 5 * 60_000).toISOString(),
    });
    render(<ProfilePage />);

    expect(
      await screen.findByText("Вход подтверждён. Теперь аккаунт можно удалить."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Удалить навсегда" })).toBeDisabled();
  });

  it("смена e-mail у аккаунта с паролем спрашивает текущий пароль", async () => {
    mockedGetMe.mockResolvedValueOnce({ ...baseUser, has_password: true });
    mockedUpdateMe.mockResolvedValueOnce({ ...baseUser, email: "new@example.com" });
    render(<ProfilePage />);

    await screen.findByText("Добро пожаловать!");
    fireEvent.click(screen.getByRole("button", { name: "Редактировать профиль" }));
    expect(screen.queryByLabelText(/Текущий пароль/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(
      await screen.findByText("Чтобы сменить e-mail, введите текущий пароль."),
    ).toBeInTheDocument();
    expect(mockedUpdateMe).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Текущий пароль/), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(mockedUpdateMe).toHaveBeenCalledWith(
        expect.objectContaining({ email: "new@example.com", current_password: "secret" }),
      ),
    );
  });

  it("смена e-mail без пароля: сервер просит подтвердить — панель в диалоге", async () => {
    mockedUpdateMe.mockRejectedValueOnce(
      Object.assign(new Error("Подтвердите"), { code: "reauth_required" }),
    );
    render(<ProfilePage />);

    await screen.findByText("Добро пожаловать!");
    fireEvent.click(screen.getByRole("button", { name: "Редактировать профиль" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(
      await screen.findByText(/Подтвердите, что это вы · \/account\/profile\?resume=edit/),
    ).toBeInTheDocument();
    expect(mockedUpdateMe.mock.calls[0][0]).not.toHaveProperty("current_password");
  });
});
