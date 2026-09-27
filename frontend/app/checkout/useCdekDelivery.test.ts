import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/delivery", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/delivery")>()),
  getCdekPoints: vi.fn(),
  quoteCdekDelivery: vi.fn(),
}));

import { getCdekPoints, quoteCdekDelivery } from "@/lib/delivery";
import { useCdekDelivery } from "./useCdekDelivery";

const mockedPoints = getCdekPoints as unknown as ReturnType<typeof vi.fn>;
const mockedQuote = quoteCdekDelivery as unknown as ReturnType<typeof vi.fn>;

const CITY = { code: 44, name: "Москва", full_name: "Москва" };

function calculated(quoteId: string) {
  return {
    ok: true,
    data: {
      quote_id: quoteId,
      status: "calculated",
      cost: "450.00",
      reason: "",
      period_min: 2,
      period_max: 4,
      address: "",
      city_name: "Москва",
      free_delivery_promo_applies: false,
    },
  };
}

describe("useCdekDelivery (DRF-2491)", () => {
  beforeEach(() => {
    mockedPoints.mockReset();
    mockedPoints.mockResolvedValue({ ok: true, data: [] });
    mockedQuote.mockReset();
    mockedQuote.mockResolvedValue(calculated("q1"));
  });

  it("смена состава корзины делает расчёт неактуальным", async () => {
    const { result, rerender } = renderHook(({ fp }) => useCdekDelivery("cdek", fp), {
      initialProps: { fp: "7:1" },
    });
    act(() => {
      result.current.setMode("cdek_courier");
      result.current.setCity(CITY);
      result.current.setAddress("ул. Ленина, 1");
    });
    await act(() => result.current.requestQuote());
    expect(result.current.quote?.quote_id).toBe("q1");

    rerender({ fp: "7:2" });
    expect(result.current.quote).toBeNull();
    expect(result.current.blocker()).toMatch(/Рассчитать доставку/);
  });

  it("поздний ответ на прежний адрес не подменяет расчёт для нового", async () => {
    let resolveFirst: (value: unknown) => void = () => {};
    mockedQuote.mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)));
    const { result } = renderHook(() => useCdekDelivery("cdek", "7:1"));
    act(() => {
      result.current.setMode("cdek_courier");
      result.current.setCity(CITY);
      result.current.setAddress("ул. Старая, 1");
    });
    let first: Promise<unknown> = Promise.resolve();
    act(() => {
      first = result.current.requestQuote();
    });
    act(() => result.current.setAddress("ул. Новая, 2"));
    await act(async () => {
      resolveFirst(calculated("old"));
      await first;
    });

    expect(result.current.quote).toBeNull();
    expect(result.current.quoting).toBe(false);
  });

  it("без расчёта поля заказа — ручные город и адрес, без quote_id", () => {
    const { result } = renderHook(() => useCdekDelivery("cdek", "7:1"));
    act(() => {
      result.current.enterFallback();
      result.current.setManualCity(" Казань ");
      result.current.setManualAddress(" ул. Баумана, 1 ");
    });
    expect(result.current.blocker()).toBeNull();
    expect(result.current.orderFields()).toEqual({
      delivery_method: "cdek_pvz",
      delivery_zone: "cdek",
      delivery_address: "Казань, ул. Баумана, 1",
    });
  });

  it("СДЭК не ответил на пункты — запасной режим с подставленным городом", async () => {
    mockedPoints.mockResolvedValue({
      ok: false,
      kind: "unavailable",
      message: "Доставка СДЭК сейчас недоступна.",
    });
    const { result } = renderHook(() => useCdekDelivery("cdek", "7:1"));
    act(() => result.current.setCity(CITY));

    await waitFor(() => expect(result.current.fallback).toBe(true));
    expect(result.current.manualCity).toBe("Москва");
  });
});
