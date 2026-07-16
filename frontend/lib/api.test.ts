import { describe, expect, it } from "vitest";

import { extractErrorMessage } from "./api";

// Сообщение об ошибке из тела Django: общий detail, пофайдовые ошибки DRF и фолбэк.
describe("extractErrorMessage", () => {
  it("берёт общий detail", () => {
    expect(extractErrorMessage({ detail: "Неверный код." }, 400)).toBe("Неверный код.");
  });

  it("собирает пофайдовые ошибки сериализатора (правила пароля)", () => {
    const body = {
      password: ["Пароль слишком короткий.", "Пароль состоит только из цифр."],
    };
    const msg = extractErrorMessage(body, 400);
    expect(msg).toContain("слишком короткий");
    expect(msg).toContain("только из цифр");
  });

  it("поддерживает строковое значение поля", () => {
    expect(extractErrorMessage({ phone: "Некорректный телефон." }, 400)).toBe(
      "Некорректный телефон.",
    );
  });

  it("фолбэк на «Ошибка N» без тела", () => {
    expect(extractErrorMessage(undefined, 500)).toBe("Ошибка 500.");
  });
});
