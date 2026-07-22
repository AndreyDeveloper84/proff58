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

  // #574: без тела ответа пользователь не должен видеть HTTP-код — только
  // понятное действие. Фолбэк подбирается по классу статуса.
  it("фолбэк без тела — человеческий текст, а не код статуса", () => {
    expect(extractErrorMessage(undefined, 500)).toBe(
      "Сервис временно недоступен. Попробуйте повторить через минуту.",
    );
    expect(extractErrorMessage(undefined, 403)).toBe("Сессия истекла. Войдите заново и повторите.");
    expect(extractErrorMessage(undefined, 404)).toBe(
      "Данные не найдены — возможно, страница устарела. Обновите её.",
    );
    expect(extractErrorMessage(undefined, 429)).toBe(
      "Слишком много попыток. Подождите минуту и повторите.",
    );
    expect(extractErrorMessage(undefined, 400)).toBe(
      "Не удалось выполнить действие. Попробуйте ещё раз.",
    );
  });
});
