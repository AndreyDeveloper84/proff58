import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CopyContact, internationalPhone, PhoneContact } from "./CopyContact";
import { ToastRegion } from "@/components/ui/ToastRegion";
import { dismissToast } from "@/lib/toast";

// UX-03: телефон и адрес копируются по нажатию, уведомление — только после успеха.
// Номер копируется на устройствах с мышью, на сенсорных — звонит по tel:.
const PHONE = "8 (8412) 20-20-87";
const PHONE_COPIED = "+7 8412 20-20-87";

// jsdom не знает matchMedia: подставляем ответ «мышь с наведением» или «палец».
function mockPointer(fine: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: fine,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
}
const ADDRESS = "г. Пенза, 1-й Онежский проезд, 12";

function setClipboard(writeText: unknown) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: writeText ? { writeText } : undefined,
  });
}

// Live-область уведомлений: всегда в разметке, внутри — только текст сообщения.
const live = () => screen.getByTestId("toast-live");
const phoneLink = () => screen.getByRole("link", { name: /8 \(8412\) 20-20-87/ });

// Клик с запоминанием, отменил ли его компонент. Сам переход по tel: гасим уже
// после проверки: jsdom навигацию не умеет и сыплет ошибками в консоль.
function dispatchClick(target: Element, pointerType?: string): boolean {
  let prevented = false;
  const record = (event: Event) => {
    prevented = event.defaultPrevented;
    event.preventDefault();
  };
  window.addEventListener("click", record);
  const click = new MouseEvent("click", { bubbles: true, cancelable: true });
  if (pointerType) Object.defineProperty(click, "pointerType", { value: pointerType });
  target.dispatchEvent(click);
  window.removeEventListener("click", record);
  return prevented;
}

function renderAll() {
  return render(
    <>
      <PhoneContact display={PHONE} href="tel:+78412202087" />
      <CopyContact kind="address" value={ADDRESS}>
        Магазин на Онежском
      </CopyContact>
      <ToastRegion />
    </>,
  );
}

describe("CopyContact (UX-03)", () => {
  beforeEach(() => {
    document.execCommand = vi.fn(() => false);
    mockPointer(true);
  });
  afterEach(() => {
    act(() => dismissToast());
    // @ts-expect-error — возвращаем jsdom его «без matchMedia».
    delete window.matchMedia;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("на ПК копирует номер в международном виде и сообщает коротко", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);
    renderAll();

    fireEvent.click(phoneLink());

    await waitFor(() => expect(live()).toHaveTextContent("Номер скопирован"));
    expect(writeText).toHaveBeenCalledWith(PHONE_COPIED);
  });

  it("по короткой подписи магазина копируется ПОЛНЫЙ адрес", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);
    renderAll();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать адрес/ }));

    await waitFor(() => expect(live()).toHaveTextContent("Адрес скопирован в буфер обмена"));
    expect(writeText).toHaveBeenCalledWith(ADDRESS);
  });

  it("уведомление об успехе не появляется, пока копирование не завершилось", async () => {
    let finish!: () => void;
    setClipboard(vi.fn(() => new Promise<void>((resolve) => (finish = resolve))));
    renderAll();

    fireEvent.click(phoneLink());
    expect(live()).toBeEmptyDOMElement();

    await act(async () => finish());
    expect(live()).toHaveTextContent("Номер скопирован");
  });

  it("запрет буфера: понятное сообщение и текст, выделенный для ручного копирования", async () => {
    setClipboard(vi.fn().mockRejectedValue(new Error("NotAllowedError")));
    renderAll();

    fireEvent.click(phoneLink());

    await waitFor(() => expect(live()).toHaveTextContent("Не удалось скопировать автоматически"));
    // Одно объявление: без role=alert внутри polite-региона.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("Номер скопирован")).not.toBeInTheDocument();
    const manual = screen.getByLabelText("Текст для копирования вручную") as HTMLInputElement;
    expect(manual.value).toBe(PHONE_COPIED);
    expect(document.activeElement).toBe(manual);
  });

  it("без Clipboard API срабатывает запасной путь, и это тоже успех", async () => {
    setClipboard(undefined);
    document.execCommand = vi.fn(() => true);
    renderAll();

    fireEvent.click(screen.getByRole("button", { name: /Скопировать адрес/ }));

    await waitFor(() => expect(live()).toHaveTextContent("Адрес скопирован"));
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });

  it("повторные нажатия не копят очередь: уведомление одно", async () => {
    setClipboard(vi.fn().mockResolvedValue(undefined));
    renderAll();
    const phone = phoneLink();

    for (let i = 0; i < 4; i++) {
      fireEvent.click(phone);
      await waitFor(() => expect(live()).toHaveTextContent("Номер скопирован"));
    }
    fireEvent.click(screen.getByRole("button", { name: /Скопировать адрес/ }));

    await waitFor(() => expect(live()).toHaveTextContent("Адрес скопирован"));
    expect(live()).not.toHaveTextContent("Номер скопирован");
    expect(screen.getAllByRole("button", { name: "Закрыть уведомление" })).toHaveLength(1);
  });

  it("уведомление само исчезает и закрывается кнопкой", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setClipboard(vi.fn().mockResolvedValue(undefined));
    renderAll();

    fireEvent.click(phoneLink());
    await waitFor(() => expect(live()).toHaveTextContent("Номер скопирован"));
    fireEvent.click(screen.getByRole("button", { name: "Закрыть уведомление" }));
    expect(live()).toBeEmptyDOMElement();

    fireEvent.click(phoneLink());
    await waitFor(() => expect(live()).toHaveTextContent("Номер скопирован"));
    act(() => vi.advanceTimersByTime(4000));
    expect(live()).toBeEmptyDOMElement();
  });

  it("номер — tel-ссылка без отдельной надписи «Позвонить», имя начинается с номера", () => {
    setClipboard(vi.fn().mockResolvedValue(undefined));
    renderAll();

    const phone = phoneLink();
    expect(phone).toHaveAttribute("href", "tel:+78412202087");
    expect(phone).toHaveAccessibleName(/^8 \(8412\) 20-20-87\s*, скопировать номер \+7 8412 20-20-87$/);
    expect(screen.queryByText("Позвонить")).not.toBeInTheDocument();
  });

  it("Enter с клавиатуры на ПК тоже копирует", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);
    renderAll();

    phoneLink().focus();
    // Enter на ссылке браузер превращает в click без pointerType.
    fireEvent.click(document.activeElement!);

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(PHONE_COPIED));
  });

  it("на сенсорном устройстве номер открывает звонок, а не копирует", () => {
    mockPointer(false);
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);
    renderAll();

    const phone = phoneLink();
    expect(phone).toHaveAccessibleName(/^8 \(8412\) 20-20-87\s*, позвонить по номеру/);
    const prevented = dispatchClick(phone);

    expect(prevented).toBe(false);
    expect(writeText).not.toHaveBeenCalled();
  });

  it("касание пальцем на ноутбуке с сенсорным экраном тоже звонит", () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);
    renderAll();

    expect(dispatchClick(phoneLink(), "touch")).toBe(false);
    expect(writeText).not.toHaveBeenCalled();
  });

  it("международный вид номера для буфера", () => {
    expect(internationalPhone("8 (8412) 20-20-87")).toBe("+7 8412 20-20-87");
    expect(internationalPhone("+7 (8412) 20-20-87")).toBe("+7 8412 20-20-87");
    expect(internationalPhone("8 800 600-44-99")).toBe("+7 800 600-44-99");
  });

  it("регион уведомлений стоит в разметке заранее и объявляется вежливо", () => {
    const { container } = renderAll();
    expect(container.querySelector('[aria-live="polite"]')).toBeInTheDocument();
  });
});
