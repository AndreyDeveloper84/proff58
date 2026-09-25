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
import { LoginForm } from "./LoginForm";
import type { OAuthProviderId } from "@/lib/oauth";

// Форма без соцвхода — как на стенде, где провайдеры ещё не включены.
function LoginPage(props: { providers?: OAuthProviderId[]; oauthError?: string; oauthProvider?: string }) {
  return (
    <LoginForm
      providers={props.providers ?? []}
      next={null}
      oauthError={props.oauthError}
      oauthProvider={props.oauthProvider}
    />
  );
}

const mockedLogin = login as unknown as ReturnType<typeof vi.fn>;
const mockedRegister = register as unknown as ReturnType<typeof vi.fn>;

function switchToRegister() {
  fireEvent.click(screen.getByRole("button", { name: /Зарегистрироваться/ }));
}

describe("Форма входа", () => {
  beforeEach(() => {
    replaceMock.mockClear();
    mockedLogin.mockClear().mockResolvedValue({});
    mockedRegister.mockClear().mockResolvedValue({});
  });

  it("вход спрашивает e-mail и пароль, а телефон — нет", () => {
    render(<LoginPage />);

    expect(screen.getByLabelText(/E-mail/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Пароль/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Телефон/)).toBeNull();
  });

  it("на входе есть ссылка «Забыли пароль?» на страницу восстановления", () => {
    render(<LoginPage />);

    expect(screen.getByRole("link", { name: "Забыли пароль?" })).toHaveAttribute(
      "href",
      "/account/forgot-password",
    );
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

  it("после входа не уводит на чужой сайт через ?next=//…", async () => {
    window.history.pushState({}, "", "/account/login?next=//evil.example/x");
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "buyer@proff58.ru" } });
    fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "StrongPass2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/account/profile"));
    window.history.pushState({}, "", "/account/login");
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

  it("ошибка входа по паролю показывается над кнопкой", async () => {
    mockedLogin.mockImplementation(() => Promise.reject(new Error("Неверный e-mail или пароль.")));
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "buyer@proff58.ru" } });
    fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));

    expect(await screen.findByText("Неверный e-mail или пароль.")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});

describe("Форма входа: вёрстка по макету", () => {
  beforeEach(() => {
    replaceMock.mockClear();
    window.history.pushState({}, "", "/account/login");
  });

  it("кнопка-глаз показывает и прячет пароль, сообщая состояние читалкам", () => {
    render(<LoginPage />);
    const input = screen.getByLabelText(/Пароль/);
    expect(input).toHaveAttribute("type", "password");

    const toggle = screen.getByRole("button", { name: "Показать пароль" });
    expect(toggle).toHaveAttribute("type", "button");
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    const hide = screen.getByRole("button", { name: "Скрыть пароль" });
    expect(hide).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(hide);
    expect(input).toHaveAttribute("type", "password");
  });

  it("поля без видимых подписей, но с placeholder", () => {
    render(<LoginPage />);
    expect(screen.getByLabelText(/E-mail/)).toHaveAttribute("placeholder", "E-mail");
    expect(screen.getByLabelText(/Пароль/)).toHaveAttribute("placeholder", "Пароль");
  });

  it("нижняя строка: «Нет аккаунта? Зарегистрироваться», в регистрации — «Уже есть аккаунт? Войти»", () => {
    render(<LoginPage />);
    expect(screen.getByText("Нет аккаунта?")).toBeInTheDocument();
    expect(screen.queryByText(/Без пароля можно войти через MAX/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Зарегистрироваться" }));
    expect(screen.getByText("Уже есть аккаунт?")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Забыли пароль?" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(screen.getByRole("heading", { name: "Вход в личный кабинет" })).toBeInTheDocument();
  });

  it("без провайдеров — нет блока «или войдите через» и согласия, остаётся «или»", () => {
    render(<LoginPage />);
    expect(screen.queryByText("или войдите через")).toBeNull();
    expect(screen.queryByText("или по e-mail")).toBeNull();
    expect(screen.queryByText(/обработку персональных данных/)).toBeNull();
    expect(screen.getByText("или")).toBeInTheDocument();
  });

  it("с провайдерами — разделители и согласие под соцкнопками", () => {
    render(<LoginPage providers={["yandex"]} />);
    expect(screen.getByText("или войдите через")).toBeInTheDocument();
    expect(screen.getByText("или по e-mail")).toBeInTheDocument();
    expect(
      screen.getByText("Продолжая, вы соглашаетесь на обработку персональных данных."),
    ).toBeInTheDocument();
  });

  it("oauth_error показывает текст и убирает код из адреса, сохраняя next", async () => {
    window.history.pushState({}, "", "/account/login?next=%2Fcart&oauth_error=email_exists&provider=vkid");
    render(<LoginPage oauthError="email_exists" oauthProvider="vkid" />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Аккаунт с этой почтой уже есть. Войдите паролем или через MAX, затем привяжите VK ID в личном кабинете.",
    );
    await waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith("/account/login?next=%2Fcart", { scroll: false }),
    );
  });

  it("неизвестный код и чужой провайдер — безопасный общий текст", async () => {
    window.history.pushState({}, "", "/account/login?oauth_error=%3Cscript%3E&provider=evil");
    render(<LoginPage oauthError="<script>" oauthProvider="evil" />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Не удалось войти. Попробуйте ещё раз или выберите другой способ.",
    );
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/account/login", { scroll: false }));
  });

  it("no_email с чужим провайдером не выводит его имя", () => {
    render(<LoginPage oauthError="no_email" oauthProvider="evil" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Сервис входа не передал адрес почты.");
    expect(alert).not.toHaveTextContent("evil");
  });

  it("без oauth_error адрес не трогаем и ошибки нет", () => {
    render(<LoginPage />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});

