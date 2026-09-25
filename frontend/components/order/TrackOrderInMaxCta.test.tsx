import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    startOrderTracking: vi.fn(),
    getOrderTrackingStatus: vi.fn(),
    maxCancel: vi.fn(),
  };
});

import { getOrderTrackingStatus, maxCancel, startOrderTracking } from "@/lib/auth";
import { TrackOrderInMaxCta } from "./TrackOrderInMaxCta";

const mockedStart = startOrderTracking as unknown as ReturnType<typeof vi.fn>;
const mockedStatus = getOrderTrackingStatus as unknown as ReturnType<typeof vi.fn>;
const mockedCancel = maxCancel as unknown as ReturnType<typeof vi.fn>;

describe("TrackOrderInMaxCta", () => {
  beforeEach(() => {
    mockedStart.mockReset();
    mockedStatus.mockReset();
    mockedCancel.mockReset();
  });

  it("клик по кнопке запускает MaxAuthFlow с правильным ctaLabel", async () => {
    mockedStart.mockResolvedValue({
      attempt_id: "a1",
      deeplink: "https://max.ru/bot?start=tok",
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      status: "pending",
    });
    mockedStatus.mockResolvedValue({ status: "pending", failure_reason: null });

    render(<TrackOrderInMaxCta orderNumber="О-1" accessToken="tok-123" />);
    fireEvent.click(screen.getByRole("button", { name: "Отслеживать заказ в MAX" }));

    await waitFor(() => expect(mockedStart).toHaveBeenCalledWith("О-1", "tok-123"));
  });

  it("после completed показывает состояние успеха", async () => {
    mockedStart.mockResolvedValue({
      attempt_id: "a2",
      deeplink: "https://max.ru/bot?start=tok2",
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      status: "pending",
    });
    mockedStatus.mockResolvedValue({ status: "completed", failure_reason: null });

    render(<TrackOrderInMaxCta orderNumber="О-2" accessToken="tok-456" />);
    fireEvent.click(screen.getByRole("button", { name: "Отслеживать заказ в MAX" }));

    await waitFor(
      () =>
        expect(
          screen.getByText("Отслеживание подключено — обновления придут в MAX"),
        ).toBeInTheDocument(),
      { timeout: 5000 },
    );
  }, 10000);
});
