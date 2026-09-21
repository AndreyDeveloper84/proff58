import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchProductFromApi } from "./adapters";

// PF-SH-RELEASE-01: карточка несёт seoIndexable из API; SSR-запросы подписаны секретом.

const BASE = "http://web:8000";
const realFetch = global.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const PRODUCT = { id: 1, slug: "p", name: "Перфоратор", price: "100.00", images: [], breadcrumb: [] };

function mockProduct(body: object, seen: Headers[] = []) {
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push(new Headers(init?.headers));
    if (String(input).includes("/compatible/")) return jsonResponse({});
    return jsonResponse(body);
  }) as typeof fetch;
}

afterEach(() => {
  global.fetch = realFetch;
  vi.unstubAllEnvs();
});

describe("fetchProductFromApi: seoIndexable", () => {
  it("true из API → индексируемая карточка", async () => {
    mockProduct({ ...PRODUCT, seo_indexable: true });
    expect((await fetchProductFromApi(BASE, "p"))?.seoIndexable).toBe(true);
  });

  it("нет поля (старый API) → fail-closed, не индексируем", async () => {
    mockProduct(PRODUCT);
    expect((await fetchProductFromApi(BASE, "p"))?.seoIndexable).toBe(false);
  });

  it("SSR-запрос карточки уходит с X-SSR-Token, если секрет задан", async () => {
    vi.stubEnv("SSR_INTERNAL_TOKEN", "s3cret");
    const seen: Headers[] = [];
    mockProduct({ ...PRODUCT, seo_indexable: true }, seen);
    await fetchProductFromApi(BASE, "p");
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((h) => h.get("X-SSR-Token") === "s3cret")).toBe(true);
  });
});
