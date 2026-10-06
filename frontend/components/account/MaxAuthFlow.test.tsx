import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({
  maxStart: vi.fn(),
  maxLinkStart: vi.fn(),
  maxStatus: vi.fn(),
  maxCancel: vi.fn(),
  maxConfirm: vi.fn(),
}));
vi.mock("qrcode", () => ({
  default: { toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,") },
}));

import { ApiError } from "@/lib/api";
import { maxConfirm, maxStart, maxStatus } from "@/lib/auth";
import { MaxAuthFlow } from "./MaxAuthFlow";

const mockedStart = maxStart as unknown as ReturnType<typeof vi.fn>;
const mockedStatus = maxStatus as unknown as ReturnType<typeof vi.fn>;
const mockedConfirm = maxConfirm as unknown as ReturnType<typeof vi.fn>;

async function begin(onCompleted = vi.fn()) {
  render(<MaxAuthFlow onCompleted={onCompleted} />);
  await act(async () => {
    fireEvent.click(screen.getByRole("button"));
  });
  return onCompleted;
}

describe("MaxAuthFlow: опрос статуса", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedStart.mockReset().mockResolvedValue({
      attempt_id: "a1",
      deeplink: "https://max.ru/bot?start=tok",
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      status: "pending",
    });
    mockedStatus.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("не шлёт новый опрос, пока не пришёл ответ на предыдущий", async () => {
    // Медленный сервер: ответ на первый опрос приходит через 9 секунд.
    let release: (v: unknown) => void = () => undefined;
    mockedStatus.mockImplementationOnce(
      () => new Promise((resolve) => (release = resolve)),
    );
    mockedStatus.mockResolvedValue({ status: "pending", failure_reason: null });
    const onCompleted = await begin();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(mockedStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      release({ status: "completed", failure_reason: null });
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(onCompleted).toHaveBeenCalledTimes(1);
    // После входа опрос остановлен: запрос со старой cookie стёр бы новую сессию.
    expect(mockedStatus).toHaveBeenCalledTimes(1);
  });

  it("продолжает опрос после pending и временной ошибки", async () => {
    mockedStatus
      .mockResolvedValueOnce({ status: "pending", failure_reason: null })
      .mockRejectedValueOnce(new Error("сеть"))
      .mockResolvedValueOnce({ status: "completed", failure_reason: null });
    const onCompleted = await begin();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500 * 3);
    });
    expect(mockedStatus).toHaveBeenCalledTimes(3);
    expect(onCompleted).toHaveBeenCalledTimes(1);
  });

  it("истёкшая ссылка останавливает опрос", async () => {
    mockedStatus.mockResolvedValue({ status: "expired", failure_reason: null });
    await begin();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500 * 4);
    });
    expect(mockedStatus).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Срок действия ссылки истёк.")).toBeInTheDocument();
  });

  // DRF-2735: причина отказа объясняется словами — раньше любое «failed» давало
  // «Не удалось подтвердить вход», и человек не понимал, что делать.
  it("причина отказа показывается текстом, который передал вызывающий", async () => {
    mockedStatus.mockResolvedValue({
      status: "failed",
      failure_reason: "phone_unverified",
    });
    render(
      <MaxAuthFlow
        onCompleted={vi.fn()}
        failureMessages={{
          phone_unverified: "Номер не подтверждён — войдите по паролю.",
        }}
      />,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500 * 2);
    });

    expect(
      screen.getByText("Номер не подтверждён — войдите по паролю."),
    ).toBeInTheDocument();
    expect(mockedStatus).toHaveBeenCalledTimes(1);
  });

  it("причина без текста — общее сообщение, а не чужое объяснение", async () => {
    // Виджет общий: при отслеживании заказа phone_mismatch — про номер заказа, и
    // текст «про аккаунт» из карты входа туда попасть не должен. Нет карты или
    // нет в ней причины — общий текст. «constructor» из прототипа — тоже.
    for (const reason of ["phone_mismatch", "constructor", null]) {
      mockedStatus
        .mockReset()
        .mockResolvedValue({ status: "failed", failure_reason: reason });
      const { unmount } = render(
        <MaxAuthFlow
          onCompleted={vi.fn()}
          failureMessages={{ no_phone: "Укажите номер." }}
        />,
      );
      await act(async () => {
        fireEvent.click(screen.getByRole("button"));
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2500 * 2);
      });
      expect(
        screen.getByText("Не удалось подтвердить вход."),
      ).toBeInTheDocument();
      unmount();
    }
  });
});

// DRF-2740: вход завершает не бот, а код из бота, введённый здесь.
describe("MaxAuthFlow: код из бота", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedStart.mockReset().mockResolvedValue({
      attempt_id: "a1",
      deeplink: "https://max.ru/bot?start=tok",
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      status: "pending",
    });
    mockedStatus
      .mockReset()
      .mockResolvedValue({
        status: "confirmation_required",
        failure_reason: null,
      });
    mockedConfirm.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("поле кода видно сразу, шестая цифра отправляет код и завершает вход", async () => {
    mockedConfirm.mockResolvedValue({
      status: "completed",
      failure_reason: null,
    });
    const onCompleted = await begin();
    const input = screen.getByLabelText("Код из MAX") as HTMLInputElement;

    await act(async () => {
      fireEvent.change(input, { target: { value: "48 29-13" } }); // нецифры отбрасываются
    });

    expect(mockedConfirm).toHaveBeenCalledWith("a1", "482913");
    expect(onCompleted).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Готово! Входим…")).toBeInTheDocument();
  });

  it("перед отправкой кода дожидается ответа на ушедший опрос и больше не опрашивает", async () => {
    let release: (v: unknown) => void = () => undefined;
    mockedStatus.mockImplementationOnce(
      () => new Promise((resolve) => (release = resolve)),
    );
    mockedConfirm.mockResolvedValue({
      status: "completed",
      failure_reason: null,
    });
    await begin();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500); // опрос ушёл и висит
    });
    expect(mockedStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Код из MAX"), {
        target: { value: "482913" },
      });
    });
    expect(mockedConfirm).not.toHaveBeenCalled(); // ждём ответ опроса

    await act(async () => {
      release({ status: "confirmation_required", failure_reason: null });
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(mockedConfirm).toHaveBeenCalledTimes(1);
    expect(mockedStatus).toHaveBeenCalledTimes(1); // после входа опрос не продолжается
  });

  it("неверный код: объясняет, сколько попыток осталось, и оставляет поле", async () => {
    mockedConfirm.mockRejectedValueOnce(
      new ApiError("Неверный код.", 400, "wrong_code", undefined, 3),
    );
    await begin();

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Код из MAX"), {
        target: { value: "000000" },
      });
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Осталось попыток: 3");
    expect(screen.getByLabelText("Код из MAX")).toBeInTheDocument();
    expect(
      (screen.getByLabelText("Код из MAX") as HTMLInputElement).value,
    ).toBe("");
  });

  it("попытки исчерпаны — попытка закрыта, предлагается начать заново", async () => {
    mockedConfirm.mockResolvedValueOnce({
      status: "failed",
      failure_reason: "code_attempts_exceeded",
    });
    await begin();

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Код из MAX"), {
        target: { value: "000000" },
      });
    });

    expect(
      screen.getByText("Не удалось подтвердить вход."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Повторить" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Код из MAX")).toBeNull();
  });

  it("409 с причиной отказа показывает текст этой причины, а не общий", async () => {
    mockedConfirm.mockRejectedValueOnce(
      new ApiError(
        "Не найдено.",
        409,
        undefined,
        undefined,
        undefined,
        "phone_mismatch",
      ),
    );
    render(
      <MaxAuthFlow
        onCompleted={vi.fn()}
        failureMessages={{
          phone_mismatch: "Номер этого MAX не совпадает с номером в профиле.",
        }}
      />,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Код из MAX"), {
        target: { value: "000000" },
      });
    });
    expect(
      screen.getByText("Номер этого MAX не совпадает с номером в профиле."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Код из MAX")).toBeNull();
  });

  it("после неверного кода опрос продолжается и ловит истечение попытки", async () => {
    mockedConfirm.mockRejectedValueOnce(
      new ApiError("Неверный код.", 400, "wrong_code", undefined, 4),
    );
    await begin();
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Код из MAX"), {
        target: { value: "000000" },
      });
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Осталось попыток: 4");
    const callsAfterError = mockedStatus.mock.calls.length;

    // Опрос жив: следующие шаги уходят и обрабатываются (бот перевыпустил код,
    // затем попытка истекла).
    mockedStatus.mockResolvedValue({ status: "expired", failure_reason: null });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(mockedStatus.mock.calls.length).toBeGreaterThan(callsAfterError);
    expect(screen.getByText("Срок действия ссылки истёк.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Код из MAX")).toBeNull();
  });

  it("без codeEntry поля нет — отслеживание заказа завершает бот", async () => {
    mockedStatus.mockResolvedValue({
      status: "completed",
      failure_reason: null,
    });
    const onCompleted = vi.fn();
    render(<MaxAuthFlow onCompleted={onCompleted} codeEntry={false} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.queryByLabelText("Код из MAX")).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(onCompleted).toHaveBeenCalledTimes(1);
  });
});
