import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/bff", () => ({ proxyToDjango: vi.fn() }));

import { proxyToDjango } from "@/lib/bff";
import { GET as listGET } from "./route";
import { POST as linkPOST } from "./[provider]/link/route";
import { POST as unlinkPOST } from "./[provider]/unlink/route";

const mockedProxy = proxyToDjango as unknown as ReturnType<typeof vi.fn>;

function ctx(provider: string) {
  return { params: Promise.resolve({ provider }) };
}

function req(path: string, method = "POST") {
  return new NextRequest(`http://localhost:3000${path}`, { method });
}

describe("BFF /api/account/oauth", () => {
  beforeEach(() => {
    mockedProxy.mockClear();
    mockedProxy.mockImplementation(() => Promise.resolve(Response.json({ ok: true })));
  });

  it("GET списка привязок проксируется в Django со слэшем", async () => {
    const request = req("/api/account/oauth", "GET");
    await listGET(request);
    expect(mockedProxy).toHaveBeenCalledWith(request, "/api/account/oauth/", { method: "GET" });
  });

  it.each(["vkid", "yandex"])("link/unlink для %s уходят в Django", async (provider) => {
    const linkReq = req(`/api/account/oauth/${provider}/link`);
    await linkPOST(linkReq, ctx(provider));
    expect(mockedProxy).toHaveBeenCalledWith(linkReq, `/api/account/oauth/${provider}/link/`, {
      method: "POST",
      body: "{}",
    });

    const unlinkReq = req(`/api/account/oauth/${provider}/unlink`);
    await unlinkPOST(unlinkReq, ctx(provider));
    expect(mockedProxy).toHaveBeenCalledWith(unlinkReq, `/api/account/oauth/${provider}/unlink/`, {
      method: "POST",
      body: "{}",
    });
  });

  it.each(["google", "..", "vkid/../admin", "VKID", ""])(
    "провайдер вне белого списка (%s) — 404 без обращения к Django",
    async (provider) => {
      const link = await linkPOST(req("/api/account/oauth/x/link"), ctx(provider));
      const unlink = await unlinkPOST(req("/api/account/oauth/x/unlink"), ctx(provider));
      expect(link.status).toBe(404);
      expect(unlink.status).toBe(404);
      expect(mockedProxy).not.toHaveBeenCalled();
    },
  );
});
