import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { YandexMap } from "./YandexMap";
import { resolveStorefront, STORE_MAP, yandexMapWidgetUrl } from "@/lib/site";

// Карта ставит метку по координатам магазина (STORE_MAP), а кнопка маршрута ведёт
// в ту же точку. У Яндекса порядок разный: ll/pt — «долгота,широта», rtext —
// «широта,долгота»; перепутанный порядок уводит метку в Сомали.

describe("YandexMap", () => {
  it("показывает метку магазина по координатам", () => {
    render(<YandexMap />);
    const url = new URL((screen.getByTitle(/Карта:/) as HTMLIFrameElement).src);

    expect(url.origin + url.pathname).toBe("https://yandex.ru/map-widget/v1/");
    expect(url.searchParams.get("ll")).toBe("44.943818,53.217561");
    expect(url.searchParams.get("pt")).toBe("44.943818,53.217561,pm2rdm");
    expect(url.searchParams.get("z")).toBe("16");
  });

  it("кнопка маршрута ведёт в ту же точку в Яндекс Картах", () => {
    render(<YandexMap />);
    const link = screen.getByRole("link", { name: "Открыть маршрут в Яндекс Картах" });
    const url = new URL(link.getAttribute("href")!);

    expect(url.origin + url.pathname).toBe("https://yandex.ru/maps/");
    expect(url.searchParams.get("rtext")).toBe("~53.217561,44.943818");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("URL из Конструктора подменяет собранный без правки компонента", () => {
    const custom = "https://yandex.ru/map-widget/v1/?um=constructor%3Aabc&source=constructor";
    expect(yandexMapWidgetUrl({ ...STORE_MAP, widgetUrl: custom })).toBe(custom);
  });

  it("фрейм подписан и грузится лениво — карта ниже первого экрана", () => {
    render(<YandexMap address="Пенза, Московская, 1" />);
    const frame = screen.getByTitle("Карта: Пенза, Московская, 1");
    expect(frame).toHaveAttribute("loading", "lazy");
  });

  it("пустой проп адреса подписывает фрейм адресом магазина", () => {
    render(<YandexMap address="   " />);
    expect(screen.getByTitle(`Карта: ${resolveStorefront().address}`)).toBeInTheDocument();
  });
});
