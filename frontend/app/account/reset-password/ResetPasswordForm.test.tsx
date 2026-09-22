import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: replaceMock }),
}));
vi.mock("@/lib/auth", () => ({ confirmPasswordReset: vi.fn() }));

import { ApiError } from "@/lib/api";
import { confirmPasswordReset } from "@/lib/auth";
import { ResetPasswordForm } from "./ResetPasswordForm";

const mocked = confirmPasswordReset as unknown as ReturnType<typeof vi.fn>;

function fill(password: string, repeat = password) {
  fireEvent.change(screen.getByLabelText("Новый пароль"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Повторите пароль"), { target: { value: repeat } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить пароль" }));
}

describe("Восстановление пароля: новый пароль", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    mocked.mockReset().mockResolvedValue(undefined);
  });

  it("без uid/token — ссылка недействительна, форма не показывается", () => {
    render(<ResetPasswordForm uid="" token="" />);
    expect(screen.getByText(/Ссылка недействительна/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Новый пароль")).toBeNull();
    expect(screen.getByRole("link", { name: /Запросить письмо заново/ })).toBeInTheDocument();
  });

  it("несовпадение паролей — ошибка без запроса на сервер", async () => {
    render(<ResetPasswordForm uid="MQ" token="abc-def" />);
    fill("StrongPass2026", "Other2026");
    expect(await screen.findByRole("alert")).toHaveTextContent("Пароли не совпадают.");
    expect(mocked).not.toHaveBeenCalled();
  });

  it("успех — экран «Пароль изменён», токен убран из адреса", async () => {
    render(<ResetPasswordForm uid="MQ" token="abc-def" />);
    fill("StrongPass2026");
    await waitFor(() => expect(mocked).toHaveBeenCalledWith("MQ", "abc-def", "StrongPass2026"));
    expect(await screen.findByText("Пароль изменён")).toBeInTheDocument();
    expect(replaceMock).toHaveBeenCalledWith("/account/reset-password?done=1");
    expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/account/login");
  });

  it("invalid_token от сервера — экран недействительной ссылки", async () => {
    mocked.mockImplementation(() =>
      Promise.reject(new ApiError("Ссылка недействительна", 400, "invalid_token")),
    );
    render(<ResetPasswordForm uid="MQ" token="abc-def" />);
    fill("StrongPass2026");
    expect(await screen.findByText(/Ссылка недействительна/)).toBeInTheDocument();
  });

  it("слабый пароль — текст ошибки сервера остаётся в форме", async () => {
    mocked.mockImplementation(() =>
      Promise.reject(new ApiError("Введённый пароль слишком короткий.", 400)),
    );
    render(<ResetPasswordForm uid="MQ" token="abc-def" />);
    fill("StrongPass2026");
    expect(await screen.findByRole("alert")).toHaveTextContent(/слишком короткий/);
    expect(screen.getByLabelText("Новый пароль")).toBeInTheDocument();
  });
});
