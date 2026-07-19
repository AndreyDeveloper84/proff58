import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
const routerMock = { push: pushMock };

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/account/profile",
}));
vi.mock("@/lib/auth", () => ({
  getMe: vi.fn(),
  getOrders: vi.fn(),
  getWishlist: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("@/components/account/MaxLinkCard", () => ({
  MaxLinkCard: () => <div>Настройки MAX</div>,
}));
vi.mock("@/components/account/NotificationPreferencesCard", () => ({
  NotificationPreferencesCard: () => <div>Настройки уведомлений</div>,
}));

import { getMe, getOrders, getWishlist } from "@/lib/auth";
import ProfilePage from "./page";

const mockedGetMe = getMe as unknown as ReturnType<typeof vi.fn>;
const mockedGetOrders = getOrders as unknown as ReturnType<typeof vi.fn>;
const mockedGetWishlist = getWishlist as unknown as ReturnType<typeof vi.fn>;

describe("ProfilePage dashboard", () => {
  beforeEach(() => {
    pushMock.mockReset();
    mockedGetMe.mockReset();
    mockedGetOrders.mockReset();
    mockedGetWishlist.mockReset();
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
        display_status: "В обработке",
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
    mockedGetMe.mockResolvedValueOnce(null);
    render(<ProfilePage />);

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/account/login"));
  });
});
