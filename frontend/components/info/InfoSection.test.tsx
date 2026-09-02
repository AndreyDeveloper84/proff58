import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InfoSection } from "./InfoSection";
import type { InfoSection as Section } from "@/lib/info-pages";

function section(patch: Partial<Section>): Section {
  return {
    layout: "",
    heading: "",
    meta: {},
    buttons: [],
    items: [],
    blocks: [],
    ...patch,
  } as Section;
}

describe("InfoSection", () => {
  it("шапка даёт единственный h1 и кнопки", () => {
    render(
      <InfoSection
        section={section({
          layout: "hero",
          heading: "Доставка",
          meta: { badge: "ПО ПЕНЗЕ" },
          buttons: [{ label: "Перейти в каталог", href: "/catalog", style: "solid" }],
          blocks: [{ kind: "text", text: "Привезём сами." }],
        })}
      />,
    );

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Доставка");
    expect(screen.getByRole("link", { name: "Перейти в каталог" })).toHaveAttribute(
      "href",
      "/catalog",
    );
  });

  it("вопрос без ответа не показывается", () => {
    render(
      <InfoSection
        section={section({
          layout: "faq",
          heading: "Вопросы",
          items: [
            { title: "Когда привезут?", text: "На следующий день." },
            { title: "Ответа пока нет?", text: "" },
          ],
        })}
      />,
    );

    // Пустой аккордеон читается как поломка сайта, а не как «ответ ещё пишут».
    expect(screen.getByText("Когда привезут?")).toBeInTheDocument();
    expect(screen.queryByText("Ответа пока нет?")).not.toBeInTheDocument();
  });

  it("секция вопросов без единого ответа исчезает целиком", () => {
    const { container } = render(
      <InfoSection
        section={section({
          layout: "faq",
          heading: "Вопросы",
          items: [{ title: "Ответа нет", text: "" }],
        })}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("шаги нумеруются сами", () => {
    render(
      <InfoSection
        section={section({
          layout: "steps",
          heading: "Что делать",
          items: [
            { title: "Позвоните", text: "" },
            { title: "Привезите", text: "" },
          ],
        })}
      />,
    );

    // Номера — часть вёрстки, а не текста: редактор не должен вбивать «01».
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getByText("02")).toBeInTheDocument();
  });

  it("неизвестный тип секции показывается текстом, а не пропадает", () => {
    render(
      <InfoSection
        section={section({
          layout: "витрина-будущего" as Section["layout"],
          heading: "Раздел",
          blocks: [{ kind: "text", text: "Текст на месте." }],
        })}
      />,
    );

    expect(screen.getByText("Текст на месте.")).toBeInTheDocument();
  });

  it("предупреждающий чеклист отличается от обычного", () => {
    const { container } = render(
      <InfoSection
        section={section({
          layout: "checklist",
          heading: "Не гарантийный случай",
          meta: { tone: "предупреждение" },
          items: [{ title: "Механические повреждения", text: "" }],
        })}
      />,
    );

    expect(container.querySelector(".bg-rating\\/5")).not.toBeNull();
  });

  it("карта берёт адрес из секции", () => {
    render(
      <InfoSection
        section={section({
          layout: "map",
          heading: "Как проехать",
          meta: { address: "Пенза, 1-й Онежский проезд, 12", phone: "8 (800) 600-44-99" },
        })}
      />,
    );

    expect(screen.getByTitle(/Карта: Пенза/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "8 (800) 600-44-99" })).toHaveAttribute(
      "href",
      "tel:88006004499",
    );
  });
});
