import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: replaceMock }),
}));
vi.mock("@/lib/auth", () => ({ login: vi.fn(), register: vi.fn() }));
// MaxAuthFlow ходит в сеть за deeplink — подменяем заглушкой.
vi.mock("@/components/account/MaxAuthFlow", () => ({
  MaxAuthFlow: () => <div data-testid="max-auth" />,
}));

import { login, register } from "@/lib/auth";
import LoginPage from "./page";

const mockedLogin = login as unknown as ReturnType<typeof vi.fn>;
const mockedRegister = register as unknown as ReturnType<typeof vi.fn>;

function switchToRegister() {
  fireEvent.click(screen.getByRole("button", { name: /Зарегистрироваться/ }));
}

describe("Форма входа", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    mockedLogin.mockReset().mockResolvedValue({});
    mockedRegister.mockReset().mockResolvedValue({});
  });

  it("вход спрашивает e-mail и пароль, а телефон — нет", () => {
    render(<LoginPage />);

    expect(screen.getByLabelText(/E-mail/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Пароль/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Телефон/)).toBeNull();
  });

  it("вход через MAX остаётся — это путь без пароля", () => {
    render(<LoginPage />);

    expect(screen.getByTestId("max-auth")).toBeInTheDocument();
  });

  it("входит по e-mail", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "buyer@proff58.ru" } });
    fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "StrongPass2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));

    await waitFor(() => expect(mockedLogin).toHaveBeenCalledWith("buyer@proff58.ru", "StrongPass2026"));
  });

  it("частное лицо регистрируется без реквизитов", async () => {
    render(<LoginPage />);
    switchToRegister();
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "person@proff58.ru" } });
    fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "StrongPass2026" } });

    expect(screen.queryByLabelText(/ИНН/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Зарегистрироваться" }));

    await waitFor(() =>
      expect(mockedRegister).toHaveBeenCalledWith(
        expect.objectContaining({ email: "person@proff58.ru", customer_type: "b2c" }),
      ),
    );
  });

  it("организация вводит реквизиты и они уходят на сервер", async () => {
    render(<LoginPage />);
    switchToRegister();
    fireEvent.click(screen.getByRole("radio", { name: "Организация" }));

    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "org@proff58.ru" } });
    fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "StrongPass2026" } });
    fireEvent.change(screen.getByLabelText(/Название организации/), {
      target: { value: "ООО «Профессионал»" },
    });
    fireEvent.change(screen.getByLabelText(/ИНН/), { target: { value: "5836123456" } });
    fireEvent.change(screen.getByLabelText(/КПП/), { target: { value: "583601001" } });
    fireEvent.click(screen.getByRole("button", { name: "Зарегистрироваться" }));

    await waitFor(() =>
      expect(mockedRegister).toHaveBeenCalledWith({
        email: "org@proff58.ru",
        password: "StrongPass2026",
        full_name: "",
        customer_type: "b2b",
        company_name: "ООО «Профессионал»",
        inn: "5836123456",
        kpp: "583601001",
      }),
    );
  });

  it("не отправляет реквизиты с некорректным КПП", async () => {
    render(<LoginPage />);
    switchToRegister();
    fireEvent.click(screen.getByRole("radio", { name: "Организация" }));

    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "org@proff58.ru" } });
    fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "StrongPass2026" } });
    fireEvent.change(screen.getByLabelText(/Название организации/), { target: { value: "ООО" } });
    fireEvent.change(screen.getByLabelText(/ИНН/), { target: { value: "5836123456" } });
    fireEvent.change(screen.getByLabelText(/КПП/), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Зарегистрироваться" }));

    expect(await screen.findByText(/КПП должен содержать 9 цифр/)).toBeInTheDocument();
    expect(mockedRegister).not.toHaveBeenCalled();
  });

  it("КПП обязателен для организации, но не для ИП", () => {
    render(<LoginPage />);
    switchToRegister();
    fireEvent.click(screen.getByRole("radio", { name: "Организация" }));

    // ИНН из 10 цифр — организация: поле обязательное.
    fireEvent.change(screen.getByLabelText(/ИНН/), { target: { value: "5836123456" } });
    expect(screen.getByLabelText(/КПП/)).toBeRequired();

    // 12 цифр — ИП, у него КПП не существует.
    fireEvent.change(screen.getByLabelText(/ИНН/), { target: { value: "583601234567" } });
    expect(screen.getByLabelText(/КПП/)).not.toBeRequired();
  });

  it("подсказывает вход через MAX вместо сброса пароля — сброса пока нет", () => {
    render(<LoginPage />);

    expect(screen.getByText(/Забыли пароль/)).toBeInTheDocument();
  });
});
