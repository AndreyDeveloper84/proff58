import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/lib/auth", () => ({ login: vi.fn(), register: vi.fn() }));
// MaxAuthFlow ходит в сеть за deeplink — подменяем заглушкой.
vi.mock("@/components/account/MaxAuthFlow", () => ({
  MaxAuthFlow: () => <div data-testid="max-auth" />,
}));
vi.mock("@/lib/oauth-providers", () => ({ getLoginOAuthProviders: vi.fn() }));

import { getLoginOAuthProviders } from "@/lib/oauth-providers";
import LoginPage from "./page";

const mockedProviders = getLoginOAuthProviders as unknown as ReturnType<typeof vi.fn>;

// Серверная страница — async-компонент: вызываем как функцию и рендерим результат.
async function renderPage(params: Record<string, string> = {}) {
  render(await LoginPage({ searchParams: Promise.resolve(params) }));
}

describe("Страница входа", () => {
  beforeEach(() => {
    mockedProviders.mockClear();
    mockedProviders.mockImplementation(() => Promise.resolve(["vkid", "yandex"]));
  });

  it("рисует кнопки только включённых провайдеров, у VK ID — ещё и Mail", async () => {
    await renderPage();

    expect(screen.getByRole("link", { name: "Войти через VK ID" })).toHaveAttribute(
      "href",
      "/api/oauth/vkid/start/",
    );
    expect(screen.getByRole("link", { name: "Войти через Mail" })).toHaveAttribute(
      "href",
      "/api/oauth/vkid/start/?via=mail_ru",
    );
    expect(screen.getByRole("link", { name: "Войти через Яндекс ID" })).toHaveAttribute(
      "href",
      "/api/oauth/yandex/start/",
    );
  });

  it("передаёт провайдеру проверенный next", async () => {
    await renderPage({ next: "/cart?step=2" });

    const next = encodeURIComponent("/cart?step=2");
    expect(screen.getByRole("link", { name: "Войти через VK ID" })).toHaveAttribute(
      "href",
      `/api/oauth/vkid/start/?next=${next}`,
    );
    expect(screen.getByRole("link", { name: "Войти через Mail" })).toHaveAttribute(
      "href",
      `/api/oauth/vkid/start/?via=mail_ru&next=${next}`,
    );
    expect(screen.getByRole("link", { name: "Войти через Яндекс ID" })).toHaveAttribute(
      "href",
      `/api/oauth/yandex/start/?next=${next}`,
    );
  });

  it("чужой next (//evil) провайдеру не передаёт", async () => {
    await renderPage({ next: "//evil.example/x" });

    expect(screen.getByRole("link", { name: "Войти через VK ID" })).toHaveAttribute(
      "href",
      "/api/oauth/vkid/start/",
    );
  });

  it("только Яндекс ID — без VK ID и Mail", async () => {
    mockedProviders.mockImplementation(() => Promise.resolve(["yandex"]));
    await renderPage();

    expect(screen.getByRole("link", { name: "Войти через Яндекс ID" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Войти через VK ID" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Войти через Mail" })).toBeNull();
  });

  it("без провайдеров блока «или войдите через» нет", async () => {
    mockedProviders.mockImplementation(() => Promise.resolve([]));
    await renderPage();

    expect(screen.queryByText("или войдите через")).toBeNull();
    expect(screen.queryByRole("link", { name: /Войти через/ })).toBeNull();
    // Вход через MAX и по паролю на месте.
    expect(screen.getByTestId("max-auth")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
  });

  it("правая колонка: четыре пункта и строка про защищённое соединение", async () => {
    await renderPage();

    const aside = screen.getByRole("complementary");
    expect(within(aside).getByRole("heading", { name: "В личном кабинете удобно" })).toBeInTheDocument();
    for (const [title, text] of [
      [
        "История и статусы заказов",
        "Следите за доставкой и получайте уведомления о каждом этапе заказа.",
      ],
      ["Счета для организаций", "Скачивайте счета на оплату в одном месте."],
      ["Избранные товары", "Сохраняйте интересные товары и возвращайтесь к ним позже."],
      [
        "Уведомления в MAX",
        "Статусы заказов и сообщения о поступлении товара — в приложении MAX.",
      ],
    ]) {
      expect(within(aside).getByText(title)).toBeInTheDocument();
      expect(within(aside).getByText(text)).toBeInTheDocument();
    }
    expect(within(aside).getByText("Данные передаются по защищённому соединению")).toBeInTheDocument();
  });

  it("«Забыли пароль?» ведёт на восстановление, заголовок — «Вход в личный кабинет»", async () => {
    await renderPage();

    expect(screen.getByRole("heading", { level: 1, name: "Вход в личный кабинет" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Забыли пароль?" })).toHaveAttribute(
      "href",
      "/account/forgot-password",
    );
  });

  it("oauth_error из адреса доходит до формы", async () => {
    await renderPage({ oauth_error: "cancelled" });

    expect(screen.getByRole("alert")).toHaveTextContent("Вход отменён.");
  });
});
