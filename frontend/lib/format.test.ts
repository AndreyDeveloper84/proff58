import { describe, expect, it } from "vitest";

import { pluralize } from "./format";

// Русская множественная форма для счётчиков («126 товаров», «1 товар», «22 товара»).
describe("pluralize", () => {
  const форма = (n: number) => pluralize(n, "товар", "товара", "товаров");

  it("one: 1, 21, 31", () => {
    expect(форма(1)).toBe("товар");
    expect(форма(21)).toBe("товар");
    expect(форма(31)).toBe("товар");
  });

  it("few: 2–4, 22–24", () => {
    expect(форма(2)).toBe("товара");
    expect(форма(4)).toBe("товара");
    expect(форма(23)).toBe("товара");
  });

  it("many: 0, 5–20, 25, 100", () => {
    expect(форма(0)).toBe("товаров");
    expect(форма(5)).toBe("товаров");
    expect(форма(11)).toBe("товаров");
    expect(форма(14)).toBe("товаров");
    expect(форма(25)).toBe("товаров");
    expect(форма(100)).toBe("товаров");
  });
});
