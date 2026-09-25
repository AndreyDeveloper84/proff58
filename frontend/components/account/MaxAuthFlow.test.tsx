import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({
  maxStart: vi.fn(),
  maxLinkStart: vi.fn(),
  maxStatus: vi.fn(),
  maxCancel: vi.fn(),
}));
vi.mock("qrcode", () => ({ default: { toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,") } }));

import { maxStart, maxStatus } from "@/lib/auth";
import { MaxAuthFlow } from "./MaxAuthFlow";

const mockedStart = maxStart as unknown as ReturnType<typeof vi.fn>;
const mockedStatus = maxStatus as unknown as ReturnType<typeof vi.fn>;

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
    mockedStatus.mockImplementationOnce(() => new Promise((resolve) => (release = resolve)));
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
});
