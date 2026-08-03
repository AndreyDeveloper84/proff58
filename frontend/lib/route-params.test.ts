import { describe, expect, it } from "vitest";

import { decodeRouteParam } from "./route-params";

describe("decodeRouteParam", () => {
  it("раскодирует кириллический номер заказа из сегмента маршрута", () => {
    // Ровно то, что Next кладёт в params для /account/orders/П-20260803-CC74CA.
    expect(decodeRouteParam("%D0%9F-20260803-CC74CA")).toBe("П-20260803-CC74CA");
  });

  it("не портит уже раскодированный номер (идемпотентность)", () => {
    expect(decodeRouteParam("П-20260803-CC74CA")).toBe("П-20260803-CC74CA");
  });

  it("возвращает битую последовательность как есть, а не падает", () => {
    // decodeURIComponent на «%» без пары цифр бросает URIError — страница из-за
    // мусора в адресе падать не должна.
    expect(decodeRouteParam("%D0%")).toBe("%D0%");
  });

  it("оставляет латинские значения без изменений", () => {
    expect(decodeRouteParam("ORD-2026-001")).toBe("ORD-2026-001");
  });
});
