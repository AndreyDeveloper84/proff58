import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// UX-05: быстрый просмотр товара из списка.
const add = vi.fn().mockResolvedValue({});
vi.mock("@/components/cart/CartProvider", () => ({ useCart: () => ({ add }) }));
// Адрес страницы меняем из теста: так проверяется закрытие окна при навигации.
let pathname = "/catalog/perforatory";
vi.mock("next/navigation", async (orig) => ({
  ...(await orig<typeof import("next/navigation")>()),
  usePathname: () => pathname,
}));
vi.mock("@/components/wishlist/WishlistProvider", () => ({
  useWishlist: () => ({ has: () => false, toggle: vi.fn(), isPending: () => false }),
}));

import { ProductCard } from "@/components/product/ProductCard";
import type { Product, ProductDetail } from "@/lib/types";
import { QuickViewProvider } from "./QuickViewProvider";

function product(patch: Partial<Product> = {}): Product {
  return {
    id: 1,
    slug: "perforator-dh24",
    name: "Перфоратор DH24PG",
    cardName: "Перфоратор DH24PG",
    brand: "Hitachi",
    specs: [{ label: "Мощность", value: "730 Вт", slug: "power" }],
    price: { final: 12990, currency: "RUB" },
    stock: "in",
    badges: [],
    ...patch,
  };
}

function detail(base: Product, patch: Partial<ProductDetail> = {}): ProductDetail {
  return {
    ...base,
    images: [
      { url: "/media/a.jpg", alt: "вид спереди", isMain: true },
      { url: "/media/b.jpg", alt: "вид сбоку", isMain: false },
    ],
    description: "",
    breadcrumb: [],
    compatible: { accessories: [], crossSell: [], analogs: [], fits: [], compatible: [] },
    specs: [
      { label: "Энергия удара", value: "2,7 Дж", slug: "energy_impact", isKey: true },
      { label: "Мощность", value: "730 Вт", slug: "power", isKey: true },
      { label: "Страна", value: "Япония", slug: "country", isKey: false },
      { label: "Тип инструмента", value: "Перфораторы", slug: "tool_type", isKey: true },
    ],
    ...patch,
  } as ProductDetail;
}

const okResponse = (d: ProductDetail) =>
  new Response(JSON.stringify({ products: [d] }), { status: 200 });

function renderList(items: Product[] = [product()]) {
  return render(
    <QuickViewProvider>
      {items.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}
    </QuickViewProvider>,
  );
}

const titleLink = (name = "Перфоратор DH24PG") =>
  screen.getAllByRole("link", { name }).find((a) => a.textContent === name)!;

describe("быстрый просмотр (UX-05)", () => {
  const originalFetch = global.fetch;
  beforeEach(() => {
    // jsdom не умеет навигацию и пишет об этом в console.error на каждом «настоящем»
    // переходе по ссылке — в тестах модификаторов это ожидаемое поведение, не ошибка.
    vi.spyOn(console, "error").mockImplementation(() => {});
    add.mockClear();
    pathname = "/catalog/perforatory";
    global.fetch = vi.fn(async () => okResponse(detail(product()))) as unknown as typeof fetch;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    global.fetch = originalFetch;
    document.body.style.overflow = "";
  });

  it("до клика подробности не запрашиваются", () => {
    renderList([product(), product({ id: 2, slug: "b", name: "Дрель" })]);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("клик по названию открывает окно: сразу цена и наличие, затем галерея и характеристики", async () => {
    renderList();
    fireEvent.click(titleLink());

    const dialog = screen.getByRole("dialog", { name: "Перфоратор DH24PG" });
    expect(within(dialog).getByText("12 990 ₽")).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/catalog/compare?slugs=perforator-dh24",
      expect.anything(),
    );

    // Порядок — backend; неключевые и служебный тип в «основные» не попадают.
    await within(dialog).findByText("Энергия удара");
    const terms = within(dialog)
      .getAllByRole("term")
      .map((t) => t.textContent);
    expect(terms).toEqual(["Энергия удара", "Мощность"]);
  });

  it("клик по фото тоже открывает окно; фото переключаются", async () => {
    renderList();
    fireEvent.click(screen.getAllByRole("link", { name: "Перфоратор DH24PG" })[0]);

    const dialog = screen.getByRole("dialog");
    await within(dialog).findByRole("button", { name: "Следующее фото" });
    expect(within(dialog).getByAltText("вид спереди")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Следующее фото" }));
    expect(within(dialog).getByAltText("вид сбоку")).toBeInTheDocument();
  });

  it.each([{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { button: 1 }])(
    "клик с модификатором %o остаётся переходом по настоящей ссылке",
    (init) => {
      renderList();
      const link = titleLink();
      expect(link).toHaveAttribute("href", "/product/perforator-dh24");

      const event = new MouseEvent("click", { bubbles: true, cancelable: true, ...init });
      link.dispatchEvent(event);

      expect(event.defaultPrevented).toBe(false);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    },
  );

  it("покупка, избранное и сравнение окно не открывают", () => {
    renderList();
    fireEvent.click(screen.getByRole("button", { name: "В избранное" }));
    fireEvent.click(screen.getByRole("button", { name: /корзин/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("покупка из окна идёт через общий CartProvider", async () => {
    renderList();
    fireEvent.click(titleLink());
    const dialog = screen.getByRole("dialog");

    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: /корзин/i }));
    });

    expect(add).toHaveBeenCalledWith(1, 1);
  });

  it("закрывается кнопкой, Escape и кликом по фону; фокус возвращается на карточку", () => {
    renderList();

    fireEvent.click(titleLink());
    fireEvent.click(screen.getByRole("button", { name: "Закрыть быстрый просмотр" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(titleLink());

    fireEvent.click(titleLink());
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(titleLink());
    fireEvent.click(screen.getByTestId("quick-view-backdrop"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Прокрутка фона разблокирована — список на прежнем месте.
    expect(document.body.style.overflow).toBe("");
  });

  it("Escape закрывает окно, даже когда фокус ушёл из него на страницу", () => {
    // Так и происходит после покупки: кнопка на время запроса disabled, и браузер
    // сбрасывает фокус на <body>. Обработчик на самом окне Escape уже не получал.
    renderList();
    fireEvent.click(titleLink());
    (document.activeElement as HTMLElement).blur();
    expect(document.activeElement).toBe(document.body);

    fireEvent.keyDown(document.body, { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Tab при фокусе вне окна возвращает фокус в окно", () => {
    renderList();
    fireEvent.click(titleLink());
    const dialog = screen.getByRole("dialog");
    (document.activeElement as HTMLElement).blur();

    fireEvent.keyDown(document.body, { key: "Tab" });

    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("клик внутри окна его не закрывает; фокус заперт в окне", () => {
    renderList();
    fireEvent.click(titleLink());
    const dialog = screen.getByRole("dialog");

    fireEvent.click(within(dialog).getByText("Быстрый просмотр"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");

    const close = within(dialog).getByRole("button", { name: "Закрыть быстрый просмотр" });
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).not.toBe(close);
  });

  it("ошибка загрузки: сообщение и «Повторить», цена из списка остаётся", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response("{}", { status: 502 }))
      .mockResolvedValueOnce(okResponse(detail(product()))) as unknown as typeof fetch;
    renderList();
    fireEvent.click(titleLink());
    const dialog = screen.getByRole("dialog");

    await within(dialog).findByRole("alert");
    expect(within(dialog).getByText("12 990 ₽")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: /Повторить/ }));
    await within(dialog).findByText("Энергия удара");
    expect(within(dialog).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("быстрое переключение: ответ предыдущего товара в окно не попадает", async () => {
    const first = product();
    const second = product({ id: 2, slug: "drel", name: "Дрель ударная", cardName: "Дрель ударная" });
    const resolvers: Record<string, (r: Response) => void> = {};
    global.fetch = vi.fn(
      (url: string) => new Promise<Response>((resolve) => (resolvers[url] = resolve)),
    ) as unknown as typeof fetch;
    renderList([first, second]);

    fireEvent.click(titleLink("Перфоратор DH24PG"));
    fireEvent.click(screen.getByRole("button", { name: "Закрыть быстрый просмотр" }));
    fireEvent.click(titleLink("Дрель ударная"));

    // Сначала приходит ЗАПОЗДАВШИЙ ответ первого товара, потом — второго.
    await act(async () => {
      resolvers["/api/catalog/compare?slugs=perforator-dh24"](okResponse(detail(first)));
    });
    await act(async () => {
      resolvers["/api/catalog/compare?slugs=drel"](
        okResponse(
          detail(second, {
            specs: [{ label: "Патрон", value: "13 мм", slug: "chuck", isKey: true }],
          }),
        ),
      );
    });

    const dialog = screen.getByRole("dialog", { name: "Дрель ударная" });
    await within(dialog).findByText("Патрон");
    expect(within(dialog).queryByText("Энергия удара")).not.toBeInTheDocument();
  });

  it("товар без фото, цены и характеристик показывает аккуратные состояния", async () => {
    const bare = product({ image: undefined, specs: [], price: { currency: "RUB" }, stock: "out" });
    global.fetch = vi.fn(async () =>
      okResponse(detail(bare, { images: [], specs: [] })),
    ) as unknown as typeof fetch;
    renderList([bare]);
    fireEvent.click(titleLink());
    const dialog = screen.getByRole("dialog");

    await within(dialog).findByText(/ещё не заполнены/);
    expect(within(dialog).getByText("Цена по запросу")).toBeInTheDocument();
    expect(within(dialog).getByText("Фото готовится")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Следующее фото" })).toBeNull();
  });

  // Окно жило в корневом layout и переживало переход: ссылка «Сообщить о поступлении»
  // и системная «Назад» меняли страницу под ним, а оно оставалось поверх.
  it("смена страницы закрывает окно, и при возврате на прежний адрес оно не всплывает", () => {
    const list = [product({ stock: "out" })];
    const tree = (items: Product[]) => (
      <QuickViewProvider>
        {items.map((p) => (
          <ProductCard key={p.id} product={p} />
        ))}
      </QuickViewProvider>
    );
    const { rerender } = render(tree(list));

    fireEvent.click(titleLink());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");

    pathname = "/product/perforator-dh24";
    rerender(tree(list));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");

    pathname = "/catalog/perforatory"; // системная «Назад»
    rerender(tree(list));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("«Подробнее о товаре» ведёт на страницу этого товара", () => {
    renderList();
    fireEvent.click(titleLink());

    expect(screen.getByRole("link", { name: /Подробнее о товаре/ })).toHaveAttribute(
      "href",
      "/product/perforator-dh24",
    );
  });

  it("без провайдера карточка остаётся обычной ссылкой", () => {
    render(<ProductCard product={product()} />);
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    titleLink().dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
  });
});
