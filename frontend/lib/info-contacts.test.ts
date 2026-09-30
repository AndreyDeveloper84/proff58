import { describe, expect, it } from "vitest";

import { INFO_PAGES, INFO_PAGE_SLUGS } from "./info-content";
import { fillContacts } from "./info-contacts";
import { resolveStorefront } from "./site";

// DRF-2495: контакты в инфо-страницах — из настроек сайта, а не из текста.

const custom = resolveStorefront({
  contacts: {
    phone_display: "8 (8412) 99-88-77",
    address: "г. Пенза, ул. Новая, 5.",
    schedule: "Пн–Пт 10:00–18:00",
    email: "shop@example.ru",
  },
});

describe("Контакты в инфо-страницах", () => {
  it("в текстах страниц нет зашитых контактов — только метки", () => {
    const raw = JSON.stringify(INFO_PAGES);
    for (const fragment of ["20-20-87", "202087", "8412", "Онежск", "penzainstrument"]) {
      expect(raw, fragment).not.toContain(fragment);
    }
    expect(raw).toContain("{{phone}}");
  });

  it("после подстановки ни одной метки не остаётся, в том числе с запасными значениями", () => {
    for (const storefront of [resolveStorefront(), custom]) {
      for (const slug of INFO_PAGE_SLUGS) {
        expect(JSON.stringify(fillContacts(INFO_PAGES[slug], storefront)), slug).not.toContain("{{");
      }
    }
  });

  // Метаданные страница берёт из сырого INFO_PAGES — метка там ушла бы в <title>.
  it("в заголовках и описаниях для поисковика меток нет", () => {
    for (const slug of INFO_PAGE_SLUGS) {
      const { title, metaTitle, metaDescription } = INFO_PAGES[slug];
      expect(`${title} ${metaTitle} ${metaDescription}`, slug).not.toContain("{{");
    }
  });

  it("значения из настроек доходят до секций, кнопок звонка и текста самовывоза", () => {
    const about = fillContacts(INFO_PAGES.about, custom);
    const map = about.sections.find((section) => section.layout === "map")!;
    expect(map.meta).toMatchObject({
      address: "г. Пенза, ул. Новая, 5",
      hours: "Пн–Пт 10:00–18:00",
      phone: "8 (8412) 99-88-77",
      email: "shop@example.ru",
    });
    const calls = about.sections.flatMap((section) =>
      section.buttons.filter((button) => button.href.startsWith("tel:")),
    );
    expect(calls.length).toBeGreaterThan(0);
    for (const button of calls) expect(button.href).toBe("tel:+78412998877");

    // Хвостовая точка адреса срезана: после метки в тексте своя пунктуация.
    const delivery = JSON.stringify(fillContacts(INFO_PAGES.delivery, custom));
    expect(delivery).toContain("г. Пенза, ул. Новая, 5. Пн–Пт 10:00–18:00. Заказ можно забрать");
  });

  it("исходные страницы не меняются, метка в значении не раскрывается повторно", () => {
    const before = JSON.stringify(INFO_PAGES.payment);
    const tricky = resolveStorefront({ contacts: { email: "{{phone}}" } });
    const filled = JSON.stringify(fillContacts(INFO_PAGES.payment, tricky));
    expect(JSON.stringify(INFO_PAGES.payment)).toBe(before);
    expect(filled).toContain('"email":"{{phone}}"');
  });
});
