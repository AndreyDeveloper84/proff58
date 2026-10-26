import { describe, expect, it } from "vitest";

import { INFO_PAGES } from "./info-content";

describe("temporary public privacy policy", () => {
  it("publishes the complete working revision without placeholder copy", () => {
    const privacy = INFO_PAGES.privacy;
    expect(privacy).toBeDefined();
    expect(privacy.title).toBe("Политика обработки персональных данных");
    expect(privacy.sections[0]?.meta.badge).toBe("ВРЕМЕННАЯ РЕДАКЦИЯ");

    const serialized = JSON.stringify(privacy);
    expect(serialized).not.toContain("ПРОЕКТ ДОКУМЕНТА");
    expect(serialized).not.toContain("Раздел заполняется юристом");
    expect(serialized).not.toContain("INTERNAL CLOSEOUT");
    expect(serialized).toContain("Индивидуальный предприниматель Шатров Алексей Григорьевич");
    expect(serialized).toContain("penzainstrument@yandex.ru");
    expect(serialized).toContain("https://proff58.ru/info/privacy");

    const numberedHeadings = privacy.sections
      .map((section) => section.heading)
      .filter((heading) => /^\d+\./.test(heading));
    expect(numberedHeadings).toHaveLength(14);
  });
});
