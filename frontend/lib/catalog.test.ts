import { afterEach, describe, expect, it, vi } from "vitest";

// API_BASE читается в catalog.ts один раз на уровне модуля, поэтому env выставляем
// ДО импорта — resetModules + динамический import (как в bff.test.ts).
async function loadCatalog(base?: string) {
  vi.resetModules();
  if (base) process.env.INTERNAL_API_BASE_URL = base;
  else delete process.env.INTERNAL_API_BASE_URL;
  return await import("./catalog");
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const TREE = [
  {
    id: 1,
    name: "Автоинструмент и гаражное оборудование",
    slug: "avto",
    sort_order: 0,
    children: [{ id: 2, name: "Домкраты", slug: "domkraty", sort_order: 0, children: [] }],
  },
];

describe("слой категорий", () => {
  const originalFetch = global.fetch;
  const originalBase = process.env.INTERNAL_API_BASE_URL;

  afterEach(() => {
    global.fetch = originalFetch;
    if (originalBase) process.env.INTERNAL_API_BASE_URL = originalBase;
    else delete process.env.INTERNAL_API_BASE_URL;
    vi.restoreAllMocks();
  });

  it("getCategoryTreeOrNull отдаёт дерево из API", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse(TREE)) as unknown as typeof fetch;
    const { getCategoryTreeOrNull } = await loadCatalog("http://web:8000");

    await expect(getCategoryTreeOrNull()).resolves.toEqual(TREE);
  });

  // Индексу каталога нужно отличать «API недоступен» от «разделов нет»: первое
  // показывает «каталог временно недоступен», второе — «разделы не заполнены».
  it("getCategoryTreeOrNull отдаёт null, когда API недоступен", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED")) as unknown as typeof fetch;
    const { getCategoryTreeOrNull } = await loadCatalog("http://web:8000");

    await expect(getCategoryTreeOrNull()).resolves.toBeNull();
  });

  // Локальная сборка без backend: показываем только разделы с фикстурой листинга,
  // чтобы ни одна карточка каталога не вела в 404.
  it("без INTERNAL_API_BASE_URL отдаёт разделы с фикстурами, а не пустоту", async () => {
    const { getCategoryTreeOrNull, listingCategories } = await loadCatalog();

    const tree = await getCategoryTreeOrNull();

    expect(tree?.map((node) => node.slug)).toEqual(listingCategories());
    expect(tree?.every((node) => node.name.length > 0)).toBe(true);
  });

  it("getCategoryLookup находит витринное имя вложенного раздела", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse(TREE)) as unknown as typeof fetch;
    const { getCategoryLookup } = await loadCatalog("http://web:8000");

    await expect(getCategoryLookup("domkraty")).resolves.toEqual({
      status: "found",
      name: "Домкраты",
    });
  });

  it("getCategoryLookup помечает несуществующий раздел как missing (→ 404)", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse(TREE)) as unknown as typeof fetch;
    const { getCategoryLookup } = await loadCatalog("http://web:8000");

    await expect(getCategoryLookup("net-takoy")).resolves.toEqual({ status: "missing" });
  });

  // Упавший API не должен превращать весь каталог в 404 — это unavailable,
  // страница рендерится с заголовком из slug.
  it("getCategoryLookup при недоступном API отдаёт unavailable, а не missing", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED")) as unknown as typeof fetch;
    const { getCategoryLookup } = await loadCatalog("http://web:8000");

    await expect(getCategoryLookup("avto")).resolves.toEqual({ status: "unavailable" });
  });
});
