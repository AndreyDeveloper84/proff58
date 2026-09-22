import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({ requestPasswordReset: vi.fn() }));

import { ApiError } from "@/lib/api";
import { requestPasswordReset } from "@/lib/auth";
import ForgotPasswordPage from "./page";

const mocked = requestPasswordReset as unknown as ReturnType<typeof vi.fn>;

function submit(email = "buyer@proff58.ru") {
  fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: "Отправить письмо" }));
}

describe("Восстановление пароля: запрос письма", () => {
  // Не mockReset: в vitest 2.1 после него отклонение из mockImplementation в этом
  // файле уходило необработанным. Чистим вызовы и задаём реализацию явно.
  beforeEach(() => {
    mocked.mockClear();
    mocked.mockImplementation(() => Promise.resolve(undefined));
  });

  it("отправляет адрес и показывает одинаковый экран «проверьте почту»", async () => {
    render(<ForgotPasswordPage />);
    submit();
    await waitFor(() => expect(mocked).toHaveBeenCalledWith("buyer@proff58.ru"));
    expect(await screen.findByText("Проверьте почту")).toBeInTheDocument();
    expect(screen.queryByLabelText(/E-mail/)).toBeNull();
  });

  it("503 — честно говорит, что письмо не ушло, и не показывает успех", async () => {
    mocked.mockImplementation(() =>
      Promise.reject(new ApiError("Сервис недоступен", 503, "email_unavailable")),
    );
    render(<ForgotPasswordPage />);
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Не удалось отправить письмо/);
    expect(screen.queryByText("Проверьте почту")).toBeNull();
  });

  it("429 — просит подождать, а не выдаёт за успех", async () => {
    mocked.mockImplementation(() => Promise.reject(new ApiError("Too many", 429)));
    render(<ForgotPasswordPage />);
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Слишком много запросов/);
  });
});
