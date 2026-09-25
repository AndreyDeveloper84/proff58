import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/oauth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/oauth")>();
  return {
    ...actual,
    getOAuthAccounts: vi.fn(),
    startOAuthLink: vi.fn(),
    unlinkOAuth: vi.fn(),
  };
});

import { ApiError } from "@/lib/api";
import { getOAuthAccounts, startOAuthLink, unlinkOAuth, type OAuthAccount } from "@/lib/oauth";
import { OAuthLinksCard } from "./OAuthLinksCard";

const mockedAccounts = getOAuthAccounts as unknown as ReturnType<typeof vi.fn>;
const mockedLink = startOAuthLink as unknown as ReturnType<typeof vi.fn>;
const mockedUnlink = unlinkOAuth as unknown as ReturnType<typeof vi.fn>;

const VK_LINKED: OAuthAccount = {
  id: "vkid",
  linked: true,
  email: "ivan@vk.com",
  linked_at: "2026-09-20T10:00:00Z",
  can_unlink: true,
};
const YANDEX_FREE: OAuthAccount = {
  id: "yandex",
  linked: false,
  email: "",
  linked_at: null,
  can_unlink: false,
};

describe("OAuthLinksCard", () => {
  const originalLocation = window.location;
  const assignMock = vi.fn();

  beforeEach(() => {
    // Правило проекта: без mockReset в паре с reject-моками — mockClear + явная реализация.
    mockedAccounts.mockClear();
    mockedAccounts.mockImplementation(() => Promise.resolve([VK_LINKED, YANDEX_FREE]));
    mockedLink.mockClear();
    mockedLink.mockImplementation(() => Promise.resolve("https://oauth.yandex.ru/authorize?x=1"));
    mockedUnlink.mockClear();
    mockedUnlink.mockImplementation(() => Promise.resolve());
    assignMock.mockClear();
    vi.spyOn(window, "confirm").mockImplementation(() => true);
    window.history.pushState({}, "", "/account/profile");
  });
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  });

  function stubAssign() {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: assignMock, search: "", pathname: "/account/profile" },
    });
  }

  it("показывает привязанного провайдера с почтой и «Привязать» у свободного", async () => {
    render(<OAuthLinksCard />);

    expect(await screen.findByText("Привязан · ivan@vk.com")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Вход через VK ID и Яндекс ID" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отвязать VK ID" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Привязать Яндекс ID" })).toBeEnabled();
  });

  it("«Привязать» уводит браузер на адрес провайдера", async () => {
    render(<OAuthLinksCard />);
    const button = await screen.findByRole("button", { name: "Привязать Яндекс ID" });
    stubAssign();

    await act(async () => {
      fireEvent.click(button);
    });

    expect(mockedLink).toHaveBeenCalledWith("yandex");
    expect(assignMock).toHaveBeenCalledWith("https://oauth.yandex.ru/authorize?x=1");
  });

  it("ошибка старта привязки (409) — показываем detail", async () => {
    mockedLink.mockImplementation(() =>
      Promise.reject(new ApiError("Яндекс ID уже привязан к этому аккаунту.", 409)),
    );
    render(<OAuthLinksCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Привязать Яндекс ID" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Яндекс ID уже привязан к этому аккаунту.",
    );
    expect(screen.getByRole("button", { name: "Привязать Яндекс ID" })).toBeEnabled();
  });

  it("«Отвязать» зовёт unlink и перечитывает список", async () => {
    render(<OAuthLinksCard />);
    const button = await screen.findByRole("button", { name: "Отвязать VK ID" });
    mockedAccounts.mockImplementation(() =>
      Promise.resolve([{ ...VK_LINKED, linked: false, email: "", linked_at: null }, YANDEX_FREE]),
    );

    fireEvent.click(button);

    await waitFor(() => expect(mockedUnlink).toHaveBeenCalledWith("vkid"));
    expect(await screen.findByRole("button", { name: "Привязать VK ID" })).toBeInTheDocument();
  });

  it("отказ в подтверждении — ничего не отвязываем", async () => {
    vi.spyOn(window, "confirm").mockImplementation(() => false);
    render(<OAuthLinksCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Отвязать VK ID" }));

    expect(mockedUnlink).not.toHaveBeenCalled();
  });

  it("can_unlink=false — кнопка выключена с подсказкой «Единственный способ входа»", async () => {
    mockedAccounts.mockImplementation(() => Promise.resolve([{ ...VK_LINKED, can_unlink: false }]));
    render(<OAuthLinksCard />);

    const button = await screen.findByRole("button", { name: "Отвязать VK ID" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Единственный способ входа");
  });

  it("400 при отвязке — показываем detail сервера", async () => {
    const detail =
      "Это единственный способ входа в аккаунт. Сначала задайте пароль или привяжите другой способ.";
    mockedUnlink.mockImplementation(() => Promise.reject(new ApiError(detail, 400)));
    render(<OAuthLinksCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Отвязать VK ID" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
  });

  it("нет включённых провайдеров — карточки нет", async () => {
    mockedAccounts.mockImplementation(() => Promise.resolve([]));
    const { container } = render(<OAuthLinksCard />);

    await waitFor(() => expect(mockedAccounts).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("?oauth_linked= — сообщение об успехе, параметр убран из адреса", async () => {
    window.history.pushState({}, "", "/account/profile?oauth_linked=vkid&tab=1");
    render(<OAuthLinksCard />);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "VK ID привязан — теперь можно входить через него.",
    );
    expect(window.location.search).toBe("?tab=1");
  });

  it.each([
    ["already_linked", "yandex", "Этот Яндекс ID уже привязан к другому аккаунту."],
    ["link_expired", null, "Привязка не завершена: войдите в аккаунт и попробуйте снова."],
    ["cancelled", null, "Вход отменён."],
    ["expired", null, "Время на вход истекло. Попробуйте ещё раз."],
    ["unavailable", null, "Этот способ входа сейчас недоступен."],
    ["whatever", "evil", "Не удалось войти. Попробуйте ещё раз или выберите другой способ."],
  ])("?oauth_error=%s — текст ошибки и чистый адрес", async (code, provider, text) => {
    const query = `oauth_error=${code}${provider ? `&provider=${provider}` : ""}`;
    window.history.pushState({}, "", `/account/profile?${query}`);
    render(<OAuthLinksCard />);

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(window.location.search).toBe("");
  });

  it("сообщение показываем, даже если провайдеры выключены", async () => {
    mockedAccounts.mockImplementation(() => Promise.resolve([]));
    window.history.pushState({}, "", "/account/profile?oauth_error=unavailable");
    render(<OAuthLinksCard />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Этот способ входа сейчас недоступен.");
  });
});
