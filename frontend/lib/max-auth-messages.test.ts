import { describe, expect, it } from "vitest";

import { MAX_LINK_FAILURES, MAX_LOGIN_FAILURES, MAX_REAUTH_FAILURES } from "./max-auth-messages";

// DRF-2735: отказ во входе по неподтверждённому номеру должен говорить, что делать.
describe("Тексты отказов MAX", () => {
  it("вход: неподтверждённый номер и аккаунт с паролем ведут в профиль", () => {
    for (const reason of ["phone_unverified", "password_account"]) {
      expect(MAX_LOGIN_FAILURES[reason]).toMatch(/по e-mail и паролю/);
      expect(MAX_LOGIN_FAILURES[reason]).toMatch(/«Вход через MAX»/);
    }
    expect(MAX_LOGIN_FAILURES.phone_unverified).toMatch(/свяжитесь с магазином/);
  });

  it("привязка: нет номера в профиле — отдельный текст, не «номер не совпадает»", () => {
    expect(MAX_LINK_FAILURES.no_phone).toMatch(/не указан номер/);
    expect(MAX_LINK_FAILURES.phone_mismatch).toMatch(/не совпадает/);
    expect(MAX_LINK_FAILURES.no_phone).not.toBe(MAX_LINK_FAILURES.phone_mismatch);
  });

  it("причины входа не подмешаны в привязку и подтверждение", () => {
    expect(MAX_LINK_FAILURES.phone_unverified).toBeUndefined();
    expect(MAX_REAUTH_FAILURES.phone_unverified).toBeUndefined();
    expect(MAX_LOGIN_FAILURES.phone_mismatch).toBeUndefined();
  });
});
