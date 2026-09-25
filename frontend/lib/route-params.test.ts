import { describe, expect, it } from "vitest";

import { decodeRouteParam } from "./route-params";

describe("decodeRouteParam", () => {
  it("возвращает номер заказа в человеческом виде", () => {
    expect(decodeRouteParam("%D0%9F-20260803-CC74CA")).toBe("П-20260803-CC74CA");
  });

  // Раскодировать уже раскодированное должно быть безопасно: вызов стоит на пути
  // каждого перехода, и второй проход не должен ничего портить.
  it("не трогает уже раскодированное значение", () => {
    expect(decodeRouteParam("П-20260803-CC74CA")).toBe("П-20260803-CC74CA");
    expect(decodeRouteParam("P-2026-0010")).toBe("P-2026-0010");
  });

  // Битую последовательность отдаём как есть: страница должна показать ошибку
  // «заказ не найден», а не упасть с URIError на этапе рендера.
  it("оборванную последовательность отдаёт как есть", () => {
    expect(decodeRouteParam("%D0%9")).toBe("%D0%9");
    expect(decodeRouteParam("100%")).toBe("100%");
  });
});
