import { afterEach, describe, expect, it, vi } from "vitest";

import { ssrHeaders } from "./ssr";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("ssrHeaders", () => {
  it("без секрета отдаёт только X-Forwarded-Proto", () => {
    vi.stubEnv("SSR_INTERNAL_TOKEN", "");
    expect(ssrHeaders()).toEqual({ "X-Forwarded-Proto": "https" });
  });

  it("с секретом добавляет X-SSR-Token (обход анонимного лимита API для SSR)", () => {
    vi.stubEnv("SSR_INTERNAL_TOKEN", "s3cret");
    expect(ssrHeaders()).toEqual({ "X-Forwarded-Proto": "https", "X-SSR-Token": "s3cret" });
  });

  it("читает секрет при вызове, а не при импорте модуля", () => {
    vi.stubEnv("SSR_INTERNAL_TOKEN", "");
    expect(ssrHeaders()["X-SSR-Token"]).toBeUndefined();
    vi.stubEnv("SSR_INTERNAL_TOKEN", "later");
    expect(ssrHeaders()["X-SSR-Token"]).toBe("later");
  });
});
