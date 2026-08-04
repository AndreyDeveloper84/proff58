import { describe, expect, it } from "vitest";

import { composeAddress, validateAddress } from "./delivery-address";

describe("composeAddress", () => {
  it("собирает строку в привычном для курьера порядке", () => {
    expect(
      composeAddress({ city: "Пенза", street: "1-й Онежский проезд", house: "12", flat: "45" }),
    ).toBe("г. Пенза, 1-й Онежский проезд, д. 12, кв. 45");
  });

  it("пустые части пропускает", () => {
    expect(composeAddress({ city: "Пенза", street: "Ленина", house: "1" })).toBe(
      "г. Пенза, Ленина, д. 1",
    );
  });

  it("добавляет подъезд и этаж, когда их указали", () => {
    expect(
      composeAddress({
        city: "Пенза",
        street: "Ленина",
        house: "1",
        flat: "2",
        entrance: "3",
        floor: "4",
      }),
    ).toBe("г. Пенза, Ленина, д. 1, кв. 2, подъезд 3, этаж 4");
  });

  // Приставку человек часто пишет сам — «г. г. Пенза» выглядело бы небрежно.
  it("не дублирует приставку, если её уже написали", () => {
    expect(composeAddress({ city: "г. Пенза", street: "Ленина", house: "д. 1" })).toBe(
      "г. Пенза, Ленина, д. 1",
    );
  });

  it("улицу не переименовывает в «ул.»", () => {
    expect(composeAddress({ city: "Пенза", street: "проспект Победы", house: "7" })).toBe(
      "г. Пенза, проспект Победы, д. 7",
    );
  });
});

describe("validateAddress", () => {
  it("полный адрес проходит", () => {
    expect(validateAddress({ city: "Пенза", street: "Ленина", house: "1" })).toBeNull();
  });

  // Ровно эти обрывки лежат в заказах на стенде: одно поле «адрес» их принимало.
  it.each([
    [{ city: "Пен", street: "", house: "" }, "улицу"],
    [{ city: "Пенза", street: "Молокова", house: "" }, "номер дома"],
    [{ city: "", street: "Ленина", house: "1" }, "город"],
  ])("неполный адрес отклоняется: %o", (parts, ожидание) => {
    expect(validateAddress(parts)).toContain(ожидание);
  });
});
