import { describe, expect, it } from "vitest";

import { serializeJsonLd } from "./jsonld";

describe("serializeJsonLd", () => {
  it("экранирует </script> — stored XSS (M-01)", () => {
    const out = serializeJsonLd({ name: "</script><script>alert(1)</script>" });
    expect(out).not.toContain("</script>");
    expect(out).not.toContain("<");
    expect(out).not.toContain(">");
    // Остаётся валидным JSON и восстанавливает исходное значение.
    expect(JSON.parse(out)).toEqual({ name: "</script><script>alert(1)</script>" });
  });

  it("экранирует & и line separators U+2028/U+2029", () => {
    const value = { d: "a & b", ls: "x y z" };
    const out = serializeJsonLd(value);
    expect(out).not.toContain("&");
    expect(out).not.toContain("\u2028");
    expect(out).not.toContain("\u2029");
    expect(JSON.parse(out)).toEqual(value);
  });

  it("не искажает обычные данные", () => {
    const value = { "@type": "Product", name: "Дрель", price: 1000 };
    expect(JSON.parse(serializeJsonLd(value))).toEqual(value);
  });
});
