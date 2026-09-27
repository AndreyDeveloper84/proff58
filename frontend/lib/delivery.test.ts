import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { cdekFailure, cdekManualText, cdekPeriodText } from "./delivery";

describe("cdekFailure (DRF-2491)", () => {
  it("400 с полем — ошибка ввода у этого поля", () => {
    expect(cdekFailure(new ApiError("Выберите пункт выдачи.", 400, undefined, "pvz_code"))).toEqual(
      { kind: "invalid", message: "Выберите пункт выдачи.", field: "pvz_code" },
    );
  });

  it("400 по зоне, 503, 502 и обрыв связи — СДЭК недоступен", () => {
    for (const error of [
      new ApiError("Доставка СДЭК сейчас недоступна.", 400, undefined, "zone"),
      new ApiError("Доставка СДЭК сейчас недоступна.", 503),
      new ApiError("Сервис временно недоступен.", 502),
      new ApiError("Нет связи с сервером.", 0),
      new SyntaxError("bad json"),
    ]) {
      expect(cdekFailure(error).kind).toBe("unavailable");
    }
  });

  it("429 — лимит запросов, а не недоступность", () => {
    expect(cdekFailure(new ApiError("Слишком много.", 429)).kind).toBe("busy");
  });
});

describe("подписи расчёта СДЭК", () => {
  it("срок: один день, диапазон, пусто", () => {
    expect(cdekPeriodText(3, 3)).toBe("3 дн.");
    expect(cdekPeriodText(2, 4)).toBe("2–4 дн.");
    expect(cdekPeriodText(null, 5)).toBe("5 дн.");
    expect(cdekPeriodText(null, null)).toBe("");
  });

  it("ручной расчёт: СДЭК не ответил — отдельный текст", () => {
    expect(cdekManualText("provider_unavailable")).toMatch(/СДЭК сейчас не отвечает/);
    expect(cdekManualText("missing_package")).toMatch(/рассчитает менеджер/);
  });
});
