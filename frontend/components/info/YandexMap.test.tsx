import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { YandexMap } from "./YandexMap";
import { resolveStorefront } from "@/lib/site";

// Карта ищет по адресу из настроек витрины, а не по зашитым координатам:
// переезд магазина не должен требовать правки кода.

describe("YandexMap", () => {
  it("ищет по адресу магазина из настроек витрины", () => {
    render(<YandexMap />);
    const frame = screen.getByTitle(/Карта:/) as HTMLIFrameElement;
    const url = new URL(frame.src);

    expect(url.origin + url.pathname).toBe("https://yandex.ru/map-widget/v1/");
    expect(url.searchParams.get("text")).toBe(resolveStorefront().address);
  });

  it("принимает свой адрес и масштаб", () => {
    render(<YandexMap address="Пенза, Московская, 1" zoom={14} />);
    const url = new URL((screen.getByTitle(/Карта:/) as HTMLIFrameElement).src);

    expect(url.searchParams.get("text")).toBe("Пенза, Московская, 1");
    expect(url.searchParams.get("z")).toBe("14");
  });

  it("грузится лениво — карта ниже первого экрана", () => {
    render(<YandexMap />);
    expect(screen.getByTitle(/Карта:/)).toHaveAttribute("loading", "lazy");
  });

  it("пустой проп адреса откатывается к адресу магазина, а не к карте мира", () => {
    render(<YandexMap address="   " />);
    const url = new URL((screen.getByTitle(/Карта:/) as HTMLIFrameElement).src);

    expect(url.searchParams.get("text")).toBe(resolveStorefront().address);
  });
});
