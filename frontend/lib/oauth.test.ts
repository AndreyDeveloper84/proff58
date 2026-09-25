import { describe, expect, it } from "vitest";
import { oauthErrorMessage, oauthLinkedMessage, oauthStartHref, pickProviders } from "./oauth";

describe("oauthStartHref", () => {
  it("без next — без параметра", () => {
    expect(oauthStartHref("yandex")).toBe("/api/oauth/yandex/start/");
    expect(oauthStartHref("vkid", { next: null })).toBe("/api/oauth/vkid/start/");
  });

  it("Mail — тот же VK ID с via=mail_ru, next кодируется", () => {
    expect(oauthStartHref("vkid", { via: "mail_ru", next: "/a b?x=1&y=2" })).toBe(
      "/api/oauth/vkid/start/?via=mail_ru&next=%2Fa%20b%3Fx%3D1%26y%3D2",
    );
  });
});

describe("oauthErrorMessage", () => {
  it("подставляет имя провайдера из белого списка", () => {
    expect(oauthErrorMessage("no_email", "yandex")).toBe(
      "Яндекс ID не передал адрес почты. Разрешите доступ к почте или войдите другим способом.",
    );
    expect(oauthErrorMessage("already_linked", "vkid")).toBe(
      "Этот VK ID уже привязан к другому аккаунту.",
    );
  });

  it("неизвестный код и служебные имена объекта — текст failed", () => {
    const failed = "Не удалось войти. Попробуйте ещё раз или выберите другой способ.";
    expect(oauthErrorMessage("nope")).toBe(failed);
    expect(oauthErrorMessage("constructor")).toBe(failed);
    expect(oauthErrorMessage("__proto__")).toBe(failed);
    expect(oauthErrorMessage(null)).toBe(failed);
  });

  it("все коды контракта дают свой текст", () => {
    expect(oauthErrorMessage("rate_limited")).toMatch(/Слишком много попыток/);
    expect(oauthErrorMessage("expired")).toBe("Время на вход истекло. Попробуйте ещё раз.");
    expect(oauthErrorMessage("inactive")).toBe("Аккаунт удалён или заблокирован.");
    expect(oauthErrorMessage("unavailable")).toBe("Этот способ входа сейчас недоступен.");
    expect(oauthErrorMessage("link_expired")).toMatch(/^Привязка не завершена/);
  });
});

describe("oauthLinkedMessage / pickProviders", () => {
  it("успех привязки только для известного провайдера", () => {
    expect(oauthLinkedMessage("vkid")).toBe("VK ID привязан — теперь можно входить через него.");
    expect(oauthLinkedMessage("evil")).toBeNull();
  });

  it("pickProviders терпит мусор", () => {
    expect(pickProviders(null)).toEqual([]);
    expect(pickProviders([null, 1, { id: "yandex" }])).toEqual(["yandex"]);
  });
});
