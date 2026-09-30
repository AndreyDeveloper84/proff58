import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({
  maxAccountStatus: vi.fn(),
  maxReauthStart: vi.fn(),
  reauthPassword: vi.fn(),
}));
vi.mock("@/lib/oauth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/oauth")>();
  return { ...actual, getOAuthAccounts: vi.fn(), startOAuthReauth: vi.fn() };
});
vi.mock("@/components/account/MaxAuthFlow", () => ({
  MaxAuthFlow: ({ ctaLabel, onCompleted }: { ctaLabel: string; onCompleted: () => void }) => (
    <button type="button" onClick={onCompleted}>
      {ctaLabel}
    </button>
  ),
}));

import { ApiError } from "@/lib/api";
import { maxAccountStatus, reauthPassword } from "@/lib/auth";
import { getOAuthAccounts, startOAuthReauth } from "@/lib/oauth";
import { ReauthPanel } from "./ReauthPanel";

const mockedMax = maxAccountStatus as unknown as ReturnType<typeof vi.fn>;
const mockedPassword = reauthPassword as unknown as ReturnType<typeof vi.fn>;
const mockedAccounts = getOAuthAccounts as unknown as ReturnType<typeof vi.fn>;
const mockedStart = startOAuthReauth as unknown as ReturnType<typeof vi.fn>;

const linked = (id: string) => ({ id, linked: true, email: "", linked_at: null, can_unlink: true });

// DRF-2497: панель «Подтвердите, что это вы» показывает только способы, которые у
// человека есть; у кого пароль — только пароль.
describe("ReauthPanel", () => {
  const originalLocation = window.location;
  const assignMock = vi.fn();

  beforeEach(() => {
    mockedMax.mockClear();
    mockedMax.mockImplementation(() => Promise.resolve({ linked: false }));
    mockedAccounts.mockClear();
    mockedAccounts.mockImplementation(() => Promise.resolve([]));
    mockedPassword.mockClear();
    mockedPassword.mockImplementation(() => Promise.resolve());
    mockedStart.mockClear();
    mockedStart.mockImplementation(() => Promise.resolve("https://id.vk.ru/authorize?x=1"));
    assignMock.mockClear();
  });
  afterEach(() => {
    Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
  });

  it("у кого пароль — только поле пароля, провайдеров не спрашиваем", async () => {
    const onVerified = vi.fn();
    render(<ReauthPanel hasPassword next="/account/profile" onVerified={onVerified} />);

    expect(screen.getByText("Введите пароль от аккаунта.")).toBeInTheDocument();
    expect(mockedMax).not.toHaveBeenCalled();
    expect(mockedAccounts).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await waitFor(() => expect(onVerified).toHaveBeenCalledTimes(1));
    expect(mockedPassword).toHaveBeenCalledWith("secret");
  });

  it("неверный пароль — сообщение сервера, onVerified не зовём", async () => {
    mockedPassword.mockImplementation(() => Promise.reject(new ApiError("Неверный пароль.", 400)));
    const onVerified = vi.fn();
    render(<ReauthPanel hasPassword next="/account/profile" onVerified={onVerified} />);
    fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "нет" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Неверный пароль.");
    expect(onVerified).not.toHaveBeenCalled();
  });

  it("без пароля — привязанные MAX и VK ID; MAX подтверждает сразу", async () => {
    mockedMax.mockImplementation(() => Promise.resolve({ linked: true }));
    mockedAccounts.mockImplementation(() =>
      Promise.resolve([linked("vkid"), { ...linked("yandex"), linked: false }]),
    );
    const onVerified = vi.fn();
    render(<ReauthPanel hasPassword={false} next="/account/profile?resume=delete" onVerified={onVerified} />);

    fireEvent.click(await screen.findByRole("button", { name: "Подтвердить через MAX" }));
    expect(onVerified).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Подтвердить через VK ID" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Подтвердить через Яндекс ID" })).toBeNull();
    expect(screen.queryByLabelText(/Пароль/)).toBeNull();
  });

  it("VK ID уводит к провайдеру с адресом возврата", async () => {
    mockedAccounts.mockImplementation(() => Promise.resolve([linked("vkid")]));
    render(<ReauthPanel hasPassword={false} next="/account/profile?resume=delete" onVerified={vi.fn()} />);
    const button = await screen.findByRole("button", { name: "Подтвердить через VK ID" });
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: assignMock },
    });

    await act(async () => {
      fireEvent.click(button);
    });
    expect(mockedStart).toHaveBeenCalledWith("vkid", "/account/profile?resume=delete");
    expect(assignMock).toHaveBeenCalledWith("https://id.vk.ru/authorize?x=1");
  });

  it("подтвердить нечем — не тупик, а контакты магазина", async () => {
    render(<ReauthPanel hasPassword={false} next="/account/profile" onVerified={vi.fn()} />);

    expect(await screen.findByText(/Подтвердить вход сейчас нечем/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "контакты" })).toHaveAttribute("href", "/info/about");
  });
});
