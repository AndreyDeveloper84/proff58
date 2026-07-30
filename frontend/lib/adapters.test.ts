import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchBestsellersFromApi,
  fetchCategoryTreeFromApi,
  fetchListingFromApi,
} from "./adapters";
import { parseQuery } from "./url-state";

const BASE = "http://web:8000";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const EMPTY_PRODUCTS = { count: 0, results: [] };

const FACETS_OK = {
  category: { name: "Автоинструмент", breadcrumb: [{ name: "Автоинструмент", slug: "avto" }] },
  subcategories: [{ name: "Домкраты", slug: "domkraty" }],
  facets: [],
  brands: [],
};

// Ответ по URL: подставляем свой мок на каждый из двух запросов листинга
// (products/ и categories/<slug>/facets/) — порядок вызовов в тестах не фиксируем.
function mockApi(routes: { products?: Response; facets?: Response }) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/catalog/products/")) {
      return routes.products ?? jsonResponse(EMPTY_PRODUCTS);
    }
    if (url.includes("/facets/")) {
      return routes.facets ?? jsonResponse(FACETS_OK);
    }
    throw new Error(`неожиданный запрос: ${url}`);
  }) as unknown as typeof fetch;
}

describe("fetchListingFromApi", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  // Раздела с таким slug нет → страница обязана уйти в notFound(), а не отдавать
  // 200 с пустым списком: products/?category=<мусор> всегда отвечает 200, поэтому
  // единственный признак — 404 от фасетов.
  it("возвращает null, когда категории нет (facets 404)", async () => {
    mockApi({ facets: jsonResponse({ detail: "Не найдено." }, 404) });

    const listing = await fetchListingFromApi(BASE, parseQuery(new URLSearchParams(), "net-takoy"));

    expect(listing).toBeNull();
  });

  it("отдаёт листинг существующей категории с названием и подкатегориями из API", async () => {
    mockApi({});

    const listing = await fetchListingFromApi(BASE, parseQuery(new URLSearchParams(), "avto"));

    expect(listing?.category.title).toBe("Автоинструмент");
    expect(listing?.subcategories).toEqual([{ label: "Домкраты", href: "/catalog/domkraty" }]);
  });

  // Фасеты — best-effort: их падение (500/сеть) не должно превращаться в 404,
  // страница рендерится со списком товаров и без фильтров.
  it("не считает категорию отсутствующей, когда фасеты упали с 500", async () => {
    mockApi({ facets: jsonResponse({ detail: "server error" }, 500) });

    const listing = await fetchListingFromApi(BASE, parseQuery(new URLSearchParams(), "avto"));

    expect(listing).not.toBeNull();
    expect(listing?.facets).toEqual([]);
  });
});

describe("fetchCategoryTreeFromApi", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("возвращает дерево категорий как есть", async () => {
    const tree = [{ id: 1, name: "Электроинструмент", slug: "elektroinstrument", sort_order: 0, children: [] }];
    global.fetch = vi.fn().mockResolvedValue(jsonResponse(tree)) as unknown as typeof fetch;

    await expect(fetchCategoryTreeFromApi(BASE)).resolves.toEqual(tree);
  });

  // null (а не []) — чтобы индекс каталога отличал «API недоступен» от «разделов нет».
  it("возвращает null при недоступном API", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({}, 502)) as unknown as typeof fetch;

    await expect(fetchCategoryTreeFromApi(BASE)).resolves.toBeNull();
  });

  it("возвращает null, когда ответ не массив", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ detail: "oops" })) as unknown as typeof fetch;

    await expect(fetchCategoryTreeFromApi(BASE)).resolves.toBeNull();
  });
});

// Витрина главной обязана называть вещи своими именами: «хиты» — только при
// реальных продажах, иначе честные новинки. Раньше блок всегда назывался
// «Хиты продаж», а данные молча приходили из ?sort=new.
describe("fetchBestsellersFromApi", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  const PRODUCT = {
    id: 1,
    name: "Перфоратор",
    slug: "perforator",
    price: "5000",
    stock_status: "in_stock",
  };

  function mockBestsellers(bestsellers: unknown[], fresh: unknown[] = []) {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/catalog/bestsellers/")) {
        return jsonResponse({ count: bestsellers.length, results: bestsellers });
      }
      if (url.includes("sort=new")) {
        return jsonResponse({ count: fresh.length, results: fresh });
      }
      throw new Error(`неожиданный запрос: ${url}`);
    }) as unknown as typeof fetch;
  }

  it("есть продажи → отдаёт хиты", async () => {
    mockBestsellers([{ ...PRODUCT, is_hit: true }]);

    const result = await fetchBestsellersFromApi(BASE, 8);

    expect(result.kind).toBe("bestsellers");
    expect(result.products).toHaveLength(1);
    expect(result.products[0].badges).toContain("hit");
  });

  it("продаж нет → новинки, помеченные как новинки", async () => {
    mockBestsellers([], [PRODUCT]);

    const result = await fetchBestsellersFromApi(BASE, 8);

    expect(result.kind).toBe("new");
    expect(result.products).toHaveLength(1);
    // Новинка не притворяется хитом.
    expect(result.products[0].badges).not.toContain("hit");
  });

  it("бейдж «Хит» ставится только по признаку backend", async () => {
    mockBestsellers([
      { ...PRODUCT, is_hit: true },
      { ...PRODUCT, id: 2, slug: "drel", is_hit: false },
    ]);

    const { products } = await fetchBestsellersFromApi(BASE, 8);

    expect(products[0].badges).toContain("hit");
    expect(products[1].badges).not.toContain("hit");
  });

  // Плитка каталога показывает телеграфную запись из 1С, страница товара —
  // развёрнутую. Товары, ещё не прошедшие normalize_product_names, card_name не
  // отдают: карточка не должна из-за этого остаться без названия.
  it("короткое имя карточки: card_name из API, иначе витринное", async () => {
    mockBestsellers([
      { ...PRODUCT, name: "Круг алмазный отрезной 115х1,0", card_name: "Круг алмаз. отрез. 115х1,0" },
      { ...PRODUCT, id: 2, slug: "bez-korotkogo", name: "Дрель ударная Makita" },
    ]);

    const { products } = await fetchBestsellersFromApi(BASE, 8);

    expect(products[0].cardName).toBe("Круг алмаз. отрез. 115х1,0");
    expect(products[0].name).toBe("Круг алмазный отрезной 115х1,0");
    expect(products[1].cardName).toBe("Дрель ударная Makita");
  });
});
